"""
智能诊断与自动修复引擎
结合日志上下文智能诊断异常根因并自动执行修复方案
"""

import asyncio
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, Any, Optional, List, Callable, Awaitable
from collections import deque

from ..llm.llm_client import LLMClient, Message

logger = logging.getLogger(__name__)


class LogLevel(Enum):
    """日志级别"""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


@dataclass
class LogEntry:
    """日志条目"""
    timestamp: datetime
    level: LogLevel
    message: str
    source: str = ""
    trace_id: Optional[str] = None
    span_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "level": self.level.value,
            "message": self.message,
            "source": self.source,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "metadata": self.metadata
        }


@dataclass
class DiagnosticResult:
    """诊断结果"""
    diagnostic_id: str
    root_cause: str
    severity: str
    affected_systems: List[str]
    suggested_fixes: List[str]
    confidence: float
    logs_analyzed: int
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "diagnostic_id": self.diagnostic_id,
            "root_cause": self.root_cause,
            "severity": self.severity,
            "affected_systems": self.affected_systems,
            "suggested_fixes": self.suggested_fixes,
            "confidence": self.confidence,
            "logs_analyzed": self.logs_analyzed,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata
        }


@dataclass
class RepairAction:
    """修复动作"""
    action_id: str
    name: str
    description: str
    action_type: str
    params: Dict[str, Any] = field(default_factory=dict)
    success: Optional[bool] = None
    result: Optional[str] = None
    executed_at: Optional[datetime] = None
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_id": self.action_id,
            "name": self.name,
            "description": self.description,
            "action_type": self.action_type,
            "params": self.params,
            "success": self.success,
            "result": self.result,
            "executed_at": self.executed_at.isoformat() if self.executed_at else None,
            "error": self.error
        }


class LogAnalyzer:
    """日志分析器"""
    
    ERROR_PATTERNS = [
        (re.compile(r"connection (timeout|refused|reset)", re.IGNORECASE), "network_connection"),
        (re.compile(r"database|mysql|postgres|sql", re.IGNORECASE), "database"),
        (re.compile(r"out of memory|heap space|OOM", re.IGNORECASE), "memory"),
        (re.compile(r"timeout|timed out", re.IGNORECASE), "timeout"),
        (re.compile(r"authentication|auth|token|credential", re.IGNORECASE), "authentication"),
        (re.compile(r"rate limit|throttl", re.IGNORECASE), "rate_limit"),
        (re.compile(r"file not found|no such file|ENOENT", re.IGNORECASE), "file_system"),
        (re.compile(r"permission|access denied|forbidden", re.IGNORECASE), "permission"),
        (re.compile(r"json|parse|decode|encode", re.IGNORECASE), "data_format"),
        (re.compile(r"null pointer|NoneType|AttributeError", re.IGNORECASE), "null_reference"),
    ]
    
    def __init__(self, max_logs: int = 10000):
        self._logs: deque = deque(maxlen=max_logs)
        self._error_logs: deque = deque(maxlen=1000)
    
    def add_log(self, entry: LogEntry):
        """添加日志"""
        self._logs.append(entry)
        if entry.level in [LogLevel.ERROR, LogLevel.CRITICAL]:
            self._error_logs.append(entry)
    
    def add_logs(self, entries: List[LogEntry]):
        """批量添加日志"""
        for entry in entries:
            self.add_log(entry)
    
    def get_logs(
        self,
        level: Optional[LogLevel] = None,
        source: Optional[str] = None,
        trace_id: Optional[str] = None,
        limit: int = 100
    ) -> List[LogEntry]:
        """获取日志"""
        logs = list(self._logs)
        
        if level:
            logs = [l for l in logs if l.level == level]
        if source:
            logs = [l for l in logs if l.source == source]
        if trace_id:
            logs = [l for l in logs if l.trace_id == trace_id]
        
        return logs[-limit:]
    
    def get_error_logs(self, limit: int = 100) -> List[LogEntry]:
        """获取错误日志"""
        return list(self._error_logs)[-limit:]
    
    def get_logs_by_trace(self, trace_id: str) -> List[LogEntry]:
        """根据追踪ID获取日志"""
        return [l for l in self._logs if l.trace_id == trace_id]
    
    def analyze_patterns(self, logs: List[LogEntry]) -> Dict[str, Any]:
        """分析日志模式"""
        pattern_counts: Dict[str, int] = {}
        error_messages: List[str] = []
        
        for entry in logs:
            if entry.level in [LogLevel.ERROR, LogLevel.CRITICAL, LogLevel.WARNING]:
                error_messages.append(entry.message)
                
                for pattern, category in self.ERROR_PATTERNS:
                    if pattern.search(entry.message):
                        pattern_counts[category] = pattern_counts.get(category, 0) + 1
        
        return {
            "pattern_counts": pattern_counts,
            "error_messages": error_messages[-50:],
            "total_errors": len([l for l in logs if l.level in [LogLevel.ERROR, LogLevel.CRITICAL]]),
            "total_warnings": len([l for l in logs if l.level == LogLevel.WARNING])
        }
    
    def get_recent_errors(self, minutes: int = 5) -> List[LogEntry]:
        """获取最近的错误"""
        cutoff = datetime.now() - datetime.timedelta(minutes=minutes)
        return [
            l for l in self._error_logs
            if l.timestamp >= cutoff
        ]


class DiagnosticEngine:
    """智能诊断引擎"""
    
    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        log_analyzer: Optional[LogAnalyzer] = None,
        auto_repair_enabled: bool = True
    ):
        self.llm_client = llm_client
        self.log_analyzer = log_analyzer or LogAnalyzer()
        self.auto_repair_enabled = auto_repair_enabled
        
        self._repair_handlers: Dict[str, Callable[[Dict[str, Any]], Awaitable[bool]]] = {}
        self._diagnostic_history: List[DiagnosticResult] = []
        self._repair_history: List[RepairAction] = []
        
        self._register_default_repair_handlers()
    
    def _register_default_repair_handlers(self):
        """注册默认修复处理器"""
        self._repair_handlers["retry_operation"] = self._handle_retry
        self._repair_handlers["reset_connection"] = self._handle_reset_connection
        self._repair_handlers["clear_cache"] = self._handle_clear_cache
        self._repair_handlers["restart_service"] = self._handle_restart_service
        self._repair_handlers["rollback_transaction"] = self._handle_rollback
    
    def register_repair_handler(
        self,
        action_type: str,
        handler: Callable[[Dict[str, Any]], Awaitable[bool]]
    ):
        """注册修复处理器"""
        self._repair_handlers[action_type] = handler
        logger.info(f"注册修复处理器: {action_type}")
    
    async def diagnose(
        self,
        logs: Optional[List[LogEntry]] = None,
        trace_id: Optional[str] = None,
        context: Optional[str] = None
    ) -> DiagnosticResult:
        """执行诊断"""
        import uuid
        
        if trace_id:
            logs = self.log_analyzer.get_logs_by_trace(trace_id)
        elif not logs:
            logs = self.log_analyzer.get_error_logs(limit=100)
        
        if not logs:
            return DiagnosticResult(
                diagnostic_id=uuid.uuid4().hex,
                root_cause="没有找到相关日志进行分析",
                severity="info",
                affected_systems=[],
                suggested_fixes=[],
                confidence=0.0,
                logs_analyzed=0
            )
        
        pattern_analysis = self.log_analyzer.analyze_patterns(logs)
        
        if self.llm_client:
            llm_result = await self._diagnose_with_llm(logs, pattern_analysis, context)
            result = DiagnosticResult(
                diagnostic_id=uuid.uuid4().hex,
                root_cause=llm_result.get("root_cause", "未知错误"),
                severity=llm_result.get("severity", "medium"),
                affected_systems=llm_result.get("affected_systems", []),
                suggested_fixes=llm_result.get("suggested_fixes", []),
                confidence=llm_result.get("confidence", 50),
                logs_analyzed=len(logs),
                metadata={"pattern_analysis": pattern_analysis}
            )
        else:
            result = self._diagnose_with_rules(pattern_analysis, logs)
        
        self._diagnostic_history.append(result)
        if len(self._diagnostic_history) > 1000:
            self._diagnostic_history = self._diagnostic_history[-500:]
        
        return result
    
    async def _diagnose_with_llm(
        self,
        logs: List[LogEntry],
        pattern_analysis: Dict[str, Any],
        context: Optional[str]
    ) -> Dict[str, Any]:
        """使用LLM进行诊断"""
        system_prompt = """你是一个专业的系统运维和日志分析专家。请分析以下日志，找出可能的问题根因，并提供修复建议。

请以JSON格式返回分析结果，包含以下字段：
- root_cause: 问题根因描述（详细说明）
- severity: 严重程度 (critical, high, medium, low)
- affected_systems: 受影响的系统列表（如OMS, WMS, TMS, Database, Network等）
- suggested_fixes: 建议的修复措施列表（每个措施是一个字符串）
- confidence: 分析置信度 (0-100的数字)

注意：
1. 分析日志中的错误模式和异常行为
2. 识别可能的根本原因，而不仅仅是表面现象
3. 提供具体、可执行的修复建议
4. 根据问题的影响范围和紧急程度评估严重程度"""
        
        log_summary = self._format_logs_for_llm(logs)
        
        user_prompt = f"""请分析以下日志：

日志摘要：
{log_summary}

模式分析结果：
{pattern_analysis}

"""
        if context:
            user_prompt += f"\n额外上下文信息：{context}"
        
        try:
            response = await self.llm_client.generate_text(
                prompt=user_prompt,
                system_prompt=system_prompt,
                temperature=0.3
            )
            
            import json
            json_start = response.find('{')
            json_end = response.rfind('}') + 1
            if json_start != -1 and json_end > json_start:
                json_str = response[json_start:json_end]
                return json.loads(json_str)
        except Exception as e:
            logger.error(f"LLM诊断失败: {e}")
        
        return {
            "root_cause": "日志分析发现异常，但无法确定具体根因",
            "severity": "medium",
            "affected_systems": [],
            "suggested_fixes": ["检查系统日志获取更多信息", "联系技术支持"],
            "confidence": 30
        }
    
    def _format_logs_for_llm(self, logs: List[LogEntry]) -> str:
        """格式化日志供LLM分析"""
        lines = []
        for entry in logs[-50:]:
            lines.append(
                f"[{entry.timestamp.strftime('%H:%M:%S')}] {entry.level.value}: {entry.message}"
            )
        return "\n".join(lines)
    
    def _diagnose_with_rules(
        self,
        pattern_analysis: Dict[str, Any],
        logs: List[LogEntry]
    ) -> DiagnosticResult:
        """使用规则进行诊断"""
        import uuid
        
        pattern_counts = pattern_analysis.get("pattern_counts", {})
        error_messages = pattern_analysis.get("error_messages", [])
        
        root_cause_parts = []
        affected_systems = []
        suggested_fixes = []
        severity = "medium"
        
        if "network_connection" in pattern_counts:
            root_cause_parts.append("网络连接问题")
            affected_systems.append("Network")
            suggested_fixes.extend([
                "检查网络连接状态",
                "验证目标服务是否可用",
                "检查防火墙和网络配置"
            ])
            severity = "high"
        
        if "database" in pattern_counts:
            root_cause_parts.append("数据库操作异常")
            affected_systems.append("Database")
            suggested_fixes.extend([
                "检查数据库连接池状态",
                "验证SQL语句正确性",
                "检查数据库锁和死锁情况"
            ])
        
        if "timeout" in pattern_counts:
            root_cause_parts.append("操作超时")
            suggested_fixes.extend([
                "增加超时时间配置",
                "检查下游服务性能",
                "考虑实现重试机制"
            ])
        
        if "authentication" in pattern_counts:
            root_cause_parts.append("认证失败")
            affected_systems.append("Security")
            suggested_fixes.extend([
                "检查API密钥和令牌有效性",
                "验证权限配置",
                "检查证书过期情况"
            ])
            severity = "critical"
        
        if "memory" in pattern_counts:
            root_cause_parts.append("内存不足")
            affected_systems.append("System")
            suggested_fixes.extend([
                "增加系统内存",
                "优化内存使用",
                "检查内存泄漏"
            ])
            severity = "critical"
        
        if not root_cause_parts:
            root_cause = "检测到异常，但无法确定具体根因"
        else:
            root_cause = "；".join(root_cause_parts)
        
        return DiagnosticResult(
            diagnostic_id=uuid.uuid4().hex,
            root_cause=root_cause,
            severity=severity,
            affected_systems=list(set(affected_systems)),
            suggested_fixes=suggested_fixes,
            confidence=60.0 if root_cause_parts else 30.0,
            logs_analyzed=len(logs),
            metadata={"pattern_analysis": pattern_analysis}
        )
    
    async def execute_repair(
        self,
        diagnostic_result: DiagnosticResult
    ) -> List[RepairAction]:
        """执行修复"""
        import uuid
        
        actions = []
        
        for fix in diagnostic_result.suggested_fixes:
            action_type = self._map_fix_to_action(fix, diagnostic_result)
            
            action = RepairAction(
                action_id=uuid.uuid4().hex,
                name=f"修复: {fix[:50]}",
                description=fix,
                action_type=action_type,
                params={
                    "diagnostic_id": diagnostic_result.diagnostic_id,
                    "root_cause": diagnostic_result.root_cause,
                    "severity": diagnostic_result.severity
                }
            )
            
            if self.auto_repair_enabled and action_type in self._repair_handlers:
                try:
                    action.executed_at = datetime.now()
                    handler = self._repair_handlers[action_type]
                    success = await handler(action.params)
                    action.success = success
                    action.result = "修复执行成功" if success else "修复执行失败"
                except Exception as e:
                    action.success = False
                    action.error = str(e)
                    logger.error(f"修复执行失败: {e}")
            
            actions.append(action)
            self._repair_history.append(action)
        
        return actions
    
    def _map_fix_to_action(self, fix: str, diagnostic: DiagnosticResult) -> str:
        """将修复建议映射到动作类型"""
        fix_lower = fix.lower()
        
        if "重试" in fix_lower or "retry" in fix_lower:
            return "retry_operation"
        elif "连接" in fix_lower or "connection" in fix_lower:
            return "reset_connection"
        elif "缓存" in fix_lower or "cache" in fix_lower:
            return "clear_cache"
        elif "重启" in fix_lower or "restart" in fix_lower:
            return "restart_service"
        elif "回滚" in fix_lower or "rollback" in fix_lower:
            return "rollback_transaction"
        
        return "manual_intervention"
    
    async def _handle_retry(self, params: Dict[str, Any]) -> bool:
        """处理重试操作"""
        logger.info(f"执行重试操作: {params}")
        await asyncio.sleep(0.1)
        return True
    
    async def _handle_reset_connection(self, params: Dict[str, Any]) -> bool:
        """处理重置连接"""
        logger.info(f"重置连接: {params}")
        await asyncio.sleep(0.1)
        return True
    
    async def _handle_clear_cache(self, params: Dict[str, Any]) -> bool:
        """处理清除缓存"""
        logger.info(f"清除缓存: {params}")
        await asyncio.sleep(0.1)
        return True
    
    async def _handle_restart_service(self, params: Dict[str, Any]) -> bool:
        """处理重启服务"""
        logger.info(f"重启服务: {params}")
        await asyncio.sleep(0.1)
        return True
    
    async def _handle_rollback(self, params: Dict[str, Any]) -> bool:
        """处理回滚"""
        logger.info(f"回滚事务: {params}")
        await asyncio.sleep(0.1)
        return True
    
    def get_diagnostic_history(self, limit: int = 100) -> List[DiagnosticResult]:
        """获取诊断历史"""
        return self._diagnostic_history[-limit:]
    
    def get_repair_history(self, limit: int = 100) -> List[RepairAction]:
        """获取修复历史"""
        return self._repair_history[-limit:]
    
    def add_log(self, entry: LogEntry):
        """添加日志"""
        self.log_analyzer.add_log(entry)
