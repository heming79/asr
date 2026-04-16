"""
REST API 接口
提供可视化动态建模和流程管理的API
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uuid

from ..orchestrator.models import (
    ProcessModel,
    Node,
    Edge,
    NodeType,
    ProcessStatus,
    ProcessInstance
)
from ..orchestrator.orchestrator import ProcessOrchestrator
from ..event_bus import EventBus, Event
from ..monitoring import MonitoringSystem, AlertLevel
from ..diagnostics import DiagnosticEngine, LogEntry, LogLevel
from ..testing import TestEngine, TestType
from ..llm.llm_client import LLMClient
from ..config.config_manager import ConfigManager
from ..adapters.oms_adapter import OMSAdapter
from ..adapters.wms_adapter import WMSAdapter
from ..adapters.tms_adapter import TMSAdapter

logger = logging.getLogger(__name__)


class NodeCreate(BaseModel):
    """节点创建请求"""
    id: str
    name: str
    type: str
    config: Dict[str, Any] = {}
    description: str = ""
    position: Dict[str, float] = {}


class EdgeCreate(BaseModel):
    """边创建请求"""
    id: str
    source: str
    target: str
    condition: Optional[str] = None
    label: str = ""


class ProcessModelCreate(BaseModel):
    """流程模型创建请求"""
    name: str
    description: str = ""
    version: str = "1.0.0"
    nodes: List[NodeCreate] = []
    edges: List[EdgeCreate] = []
    variables: Dict[str, Any] = {}


class ProcessStartRequest(BaseModel):
    """流程启动请求"""
    variables: Dict[str, Any] = {}


class AlertCreate(BaseModel):
    """告警创建请求"""
    name: str
    level: str
    message: str
    source: str
    metadata: Dict[str, Any] = {}


class LogEntryCreate(BaseModel):
    """日志创建请求"""
    level: str
    message: str
    source: str = ""
    trace_id: Optional[str] = None
    metadata: Dict[str, Any] = {}


class AIAgentApp:
    """AI Agent 应用"""
    
    def __init__(self):
        self.config_manager: Optional[ConfigManager] = None
        self.llm_client: Optional[LLMClient] = None
        self.event_bus: Optional[EventBus] = None
        self.monitoring: Optional[MonitoringSystem] = None
        self.diagnostic_engine: Optional[DiagnosticEngine] = None
        self.test_engine: Optional[TestEngine] = None
        
        self.process_models: Dict[str, ProcessModel] = {}
        self.orchestrators: Dict[str, ProcessOrchestrator] = {}
        
        self.adapters: Dict[str, Any] = {}
    
    async def initialize(self):
        """初始化应用"""
        self.config_manager = ConfigManager()
        
        self.event_bus = EventBus()
        self.event_bus.start(worker_count=3)
        
        self.monitoring = MonitoringSystem()
        self.monitoring.start()
        
        self.diagnostic_engine = DiagnosticEngine(
            llm_client=None,
            auto_repair_enabled=True
        )
        
        self.test_engine = TestEngine(llm_client=None)
        
        self._setup_event_listeners()
        
        logger.info("AI Agent 应用初始化完成")
    
    def _setup_event_listeners(self):
        """设置事件监听器"""
        if not self.event_bus:
            return
        
        async def on_process_completed(event: Event):
            if self.monitoring:
                self.monitoring.increment_counter(
                    type(self.monitoring).MetricType.PROCESS_COMPLETED
                )
            logger.info(f"流程完成: {event.data.get('id')}")
        
        async def on_process_failed(event: Event):
            if self.monitoring:
                self.monitoring.increment_counter(
                    type(self.monitoring).MetricType.PROCESS_FAILED
                )
            
            if self.diagnostic_engine:
                trace_id = event.data.get("id")
                await self.diagnostic_engine.diagnose(trace_id=trace_id)
            
            logger.error(f"流程失败: {event.data.get('id')}")
        
        self.event_bus.subscribe("process.completed", on_process_completed)
        self.event_bus.subscribe("process.failed", on_process_failed)
    
    def configure_llm(self, force_prompt: bool = False) -> bool:
        """配置大模型"""
        if not self.config_manager:
            return False
        
        if not force_prompt and self.config_manager.check_llm_configured():
            llm_config = self.config_manager.get_llm_config()
        else:
            llm_config = self.config_manager.prompt_for_llm_config()
        
        if llm_config and llm_config.api_key:
            self.llm_client = LLMClient(llm_config)
            self.diagnostic_engine = DiagnosticEngine(
                llm_client=self.llm_client,
                auto_repair_enabled=True
            )
            self.test_engine = TestEngine(llm_client=self.llm_client)
            logger.info("大模型配置完成")
            return True
        
        return False
    
    def create_process_model(self, data: ProcessModelCreate) -> ProcessModel:
        """创建流程模型"""
        model_id = f"pm_{uuid.uuid4().hex[:8]}"
        
        nodes = []
        for node_data in data.nodes:
            try:
                node_type = NodeType(node_data.type)
            except ValueError:
                node_type = NodeType.TASK
            
            nodes.append(Node(
                id=node_data.id,
                name=node_data.name,
                type=node_type,
                config=node_data.config,
                description=node_data.description,
                position=node_data.position
            ))
        
        edges = []
        for edge_data in data.edges:
            edges.append(Edge(
                id=edge_data.id,
                source=edge_data.source,
                target=edge_data.target,
                condition=edge_data.condition,
                label=edge_data.label
            ))
        
        model = ProcessModel(
            id=model_id,
            name=data.name,
            version=data.version,
            description=data.description,
            nodes=nodes,
            edges=edges,
            variables=data.variables
        )
        
        self.process_models[model_id] = model
        
        orchestrator = ProcessOrchestrator(
            process_model=model,
            event_bus=self.event_bus,
            monitoring=self.monitoring,
            adapters=self.adapters
        )
        self.orchestrators[model_id] = orchestrator
        
        logger.info(f"创建流程模型: {model_id} ({data.name})")
        return model
    
    def get_process_model(self, model_id: str) -> Optional[ProcessModel]:
        """获取流程模型"""
        return self.process_models.get(model_id)
    
    def get_all_process_models(self) -> List[ProcessModel]:
        """获取所有流程模型"""
        return list(self.process_models.values())
    
    async def start_process(
        self,
        model_id: str,
        variables: Dict[str, Any]
    ) -> ProcessInstance:
        """启动流程"""
        orchestrator = self.orchestrators.get(model_id)
        if not orchestrator:
            raise ValueError(f"流程模型不存在: {model_id}")
        
        instance = await orchestrator.start_process(variables=variables)
        return instance
    
    def get_process_instance(self, model_id: str, instance_id: str) -> Optional[ProcessInstance]:
        """获取流程实例"""
        orchestrator = self.orchestrators.get(model_id)
        if not orchestrator:
            return None
        return orchestrator.get_process_instance(instance_id)
    
    def setup_adapters(self, system_config: Dict[str, Any]):
        """设置系统适配器"""
        oms_config = system_config.get("oms", {})
        if oms_config:
            self.adapters["oms"] = OMSAdapter(oms_config)
        
        wms_config = system_config.get("wms", {})
        if wms_config:
            self.adapters["wms"] = WMSAdapter(wms_config)
        
        tms_config = system_config.get("tms", {})
        if tms_config:
            self.adapters["tms"] = TMSAdapter(tms_config)
        
        logger.info(f"系统适配器配置完成: {list(self.adapters.keys())}")
    
    async def shutdown(self):
        """关闭应用"""
        if self.event_bus:
            await self.event_bus.stop()
        
        if self.monitoring:
            await self.monitoring.stop()
        
        logger.info("AI Agent 应用已关闭")


app_state: Optional[AIAgentApp] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    global app_state
    
    app_state = AIAgentApp()
    await app_state.initialize()
    
    yield
    
    await app_state.shutdown()


def create_app() -> FastAPI:
    """创建FastAPI应用"""
    app = FastAPI(
        title="企业级流程编排AI智能体",
        description="电商订单跨系统(OMS/WMS/TMS)自动化协同平台",
        version="1.0.0",
        lifespan=lifespan
    )
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    @app.get("/")
    async def root():
        """根路径"""
        return {
            "name": "企业级流程编排AI智能体",
            "version": "1.0.0",
            "status": "running",
            "timestamp": datetime.now().isoformat()
        }
    
    @app.get("/health")
    async def health_check():
        """健康检查"""
        if app_state and app_state.monitoring:
            return app_state.monitoring.get_health_status()
        return {"status": "healthy", "timestamp": datetime.now().isoformat()}
    
    @app.post("/api/config/llm")
    async def configure_llm(force_prompt: bool = False):
        """配置大模型"""
        if not app_state:
            raise HTTPException(status_code=500, detail="应用未初始化")
        
        success = app_state.configure_llm(force_prompt=force_prompt)
        return {
            "success": success,
            "message": "大模型配置完成" if success else "配置失败"
        }
    
    @app.get("/api/config/llm/status")
    async def get_llm_status():
        """获取大模型配置状态"""
        if not app_state or not app_state.config_manager:
            return {"configured": False}
        
        return {
            "configured": app_state.config_manager.check_llm_configured()
        }
    
    @app.post("/api/process/models")
    async def create_process_model(data: ProcessModelCreate):
        """创建流程模型"""
        if not app_state:
            raise HTTPException(status_code=500, detail="应用未初始化")
        
        try:
            model = app_state.create_process_model(data)
            return model.to_dict()
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
    
    @app.get("/api/process/models")
    async def list_process_models():
        """获取所有流程模型"""
        if not app_state:
            raise HTTPException(status_code=500, detail="应用未初始化")
        
        models = app_state.get_all_process_models()
        return {"models": [m.to_dict() for m in models], "total": len(models)}
    
    @app.get("/api/process/models/{model_id}")
    async def get_process_model(model_id: str):
        """获取流程模型详情"""
        if not app_state:
            raise HTTPException(status_code=500, detail="应用未初始化")
        
        model = app_state.get_process_model(model_id)
        if not model:
            raise HTTPException(status_code=404, detail="流程模型不存在")
        
        return model.to_dict()
    
    @app.post("/api/process/models/{model_id}/validate")
    async def validate_process_model(model_id: str):
        """验证流程模型"""
        if not app_state:
            raise HTTPException(status_code=500, detail="应用未初始化")
        
        model = app_state.get_process_model(model_id)
        if not model:
            raise HTTPException(status_code=404, detail="流程模型不存在")
        
        errors = model.validate()
        return {
            "valid": len(errors) == 0,
            "errors": errors
        }
    
    @app.post("/api/process/models/{model_id}/start")
    async def start_process(model_id: str, data: ProcessStartRequest, background_tasks: BackgroundTasks):
        """启动流程实例"""
        if not app_state:
            raise HTTPException(status_code=500, detail="应用未初始化")
        
        try:
            instance = await app_state.start_process(model_id, data.variables)
            return instance.to_dict()
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
    
    @app.get("/api/process/models/{model_id}/instances/{instance_id}")
    async def get_process_instance(model_id: str, instance_id: str):
        """获取流程实例详情"""
        if not app_state:
            raise HTTPException(status_code=500, detail="应用未初始化")
        
        instance = app_state.get_process_instance(model_id, instance_id)
        if not instance:
            raise HTTPException(status_code=404, detail="流程实例不存在")
        
        return instance.to_dict()
    
    @app.get("/api/monitoring/metrics")
    async def get_metrics():
        """获取监控指标"""
        if not app_state or not app_state.monitoring:
            raise HTTPException(status_code=500, detail="监控系统未初始化")
        
        return app_state.monitoring.get_metrics_summary()
    
    @app.get("/api/monitoring/alerts")
    async def get_alerts(active_only: bool = True):
        """获取告警"""
        if not app_state or not app_state.monitoring:
            raise HTTPException(status_code=500, detail="监控系统未初始化")
        
        if active_only:
            alerts = app_state.monitoring.get_active_alerts()
        else:
            alerts = app_state.monitoring.get_alert_history()
        
        return {"alerts": [a.to_dict() for a in alerts], "total": len(alerts)}
    
    @app.post("/api/monitoring/alerts")
    async def create_alert(data: AlertCreate):
        """创建告警"""
        if not app_state or not app_state.monitoring:
            raise HTTPException(status_code=500, detail="监控系统未初始化")
        
        try:
            level = AlertLevel(data.level)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"无效的告警级别: {data.level}")
        
        alert = app_state.monitoring.create_alert(
            name=data.name,
            level=level,
            message=data.message,
            source=data.source,
            metadata=data.metadata
        )
        
        return alert.to_dict()
    
    @app.post("/api/monitoring/alerts/{alert_id}/resolve")
    async def resolve_alert(alert_id: str):
        """解决告警"""
        if not app_state or not app_state.monitoring:
            raise HTTPException(status_code=500, detail="监控系统未初始化")
        
        success = app_state.monitoring.resolve_alert(alert_id)
        return {"success": success}
    
    @app.post("/api/diagnostics/logs")
    async def add_log(data: LogEntryCreate):
        """添加日志"""
        if not app_state or not app_state.diagnostic_engine:
            raise HTTPException(status_code=500, detail="诊断引擎未初始化")
        
        try:
            level = LogLevel(data.level)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"无效的日志级别: {data.level}")
        
        entry = LogEntry(
            timestamp=datetime.now(),
            level=level,
            message=data.message,
            source=data.source,
            trace_id=data.trace_id,
            metadata=data.metadata
        )
        
        app_state.diagnostic_engine.add_log(entry)
        return {"success": True}
    
    @app.post("/api/diagnostics/analyze")
    async def analyze_logs(trace_id: Optional[str] = None):
        """分析日志并诊断问题"""
        if not app_state or not app_state.diagnostic_engine:
            raise HTTPException(status_code=500, detail="诊断引擎未初始化")
        
        result = await app_state.diagnostic_engine.diagnose(trace_id=trace_id)
        return result.to_dict()
    
    @app.post("/api/diagnostics/repair/{diagnostic_id}")
    async def execute_repair(diagnostic_id: str):
        """执行修复"""
        if not app_state or not app_state.diagnostic_engine:
            raise HTTPException(status_code=500, detail="诊断引擎未初始化")
        
        history = app_state.diagnostic_engine.get_diagnostic_history()
        diagnostic = next((d for d in history if d.diagnostic_id == diagnostic_id), None)
        
        if not diagnostic:
            raise HTTPException(status_code=404, detail="诊断结果不存在")
        
        actions = await app_state.diagnostic_engine.execute_repair(diagnostic)
        return {"actions": [a.to_dict() for a in actions]}
    
    @app.post("/api/testing/generate/{model_id}")
    async def generate_tests(model_id: str):
        """基于流程模型生成测试用例"""
        if not app_state or not app_state.test_engine:
            raise HTTPException(status_code=500, detail="测试引擎未初始化")
        
        model = app_state.get_process_model(model_id)
        if not model:
            raise HTTPException(status_code=404, detail="流程模型不存在")
        
        suite = await app_state.test_engine.generate_and_run_tests(model)
        return {
            "suite": suite.suite_id,
            "test_cases": [tc.to_dict() for tc in suite.test_cases],
            "results": {k: v.to_dict() for k, v in suite.test_results.items()},
            "summary": suite.get_result_summary()
        }
    
    @app.get("/api/testing/statistics")
    async def get_test_statistics():
        """获取测试统计"""
        if not app_state or not app_state.test_engine:
            raise HTTPException(status_code=500, detail="测试引擎未初始化")
        
        return app_state.test_engine.get_test_statistics()
    
    @app.post("/api/adapters/setup")
    async def setup_adapters(config: Dict[str, Any]):
        """设置系统适配器"""
        if not app_state:
            raise HTTPException(status_code=500, detail="应用未初始化")
        
        app_state.setup_adapters(config)
        return {
            "success": True,
            "adapters": list(app_state.adapters.keys())
        }
    
    @app.get("/api/adapters/health")
    async def check_adapters_health():
        """检查适配器健康状态"""
        if not app_state:
            raise HTTPException(status_code=500, detail="应用未初始化")
        
        health_status = {}
        for name, adapter in app_state.adapters.items():
            try:
                healthy = await adapter.health_check()
                health_status[name] = {"healthy": healthy}
            except Exception as e:
                health_status[name] = {"healthy": False, "error": str(e)}
        
        return health_status
    
    return app
