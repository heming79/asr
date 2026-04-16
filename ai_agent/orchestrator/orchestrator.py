"""
流程编排器核心实现
负责流程的执行、调度和状态管理
"""

import uuid
import logging
import asyncio
from datetime import datetime
from typing import Optional, List, Dict, Any, Callable, Awaitable
from abc import ABC, abstractmethod

from .models import (
    ProcessModel,
    Node,
    Edge,
    NodeType,
    ProcessStatus,
    NodeStatus,
    ProcessInstance,
    NodeInstance
)
from ..event_bus import EventBus, Event
from ..monitoring import MonitoringSystem, MetricType

logger = logging.getLogger(__name__)


class NodeHandler(ABC):
    """节点处理器基类"""
    
    def __init__(self, orchestrator: 'ProcessOrchestrator'):
        self.orchestrator = orchestrator
    
    @abstractmethod
    async def execute(
        self,
        node: Node,
        node_instance: NodeInstance,
        process_instance: ProcessInstance,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """执行节点"""
        pass


class StartNodeHandler(NodeHandler):
    """开始节点处理器"""
    
    async def execute(
        self,
        node: Node,
        node_instance: NodeInstance,
        process_instance: ProcessInstance,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        logger.info(f"执行开始节点: {node.id}")
        return {"status": "started"}


class EndNodeHandler(NodeHandler):
    """结束节点处理器"""
    
    async def execute(
        self,
        node: Node,
        node_instance: NodeInstance,
        process_instance: ProcessInstance,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        logger.info(f"执行结束节点: {node.id}")
        return {"status": "ended"}


class TaskNodeHandler(NodeHandler):
    """任务节点处理器"""
    
    async def execute(
        self,
        node: Node,
        node_instance: NodeInstance,
        process_instance: ProcessInstance,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        logger.info(f"执行任务节点: {node.id} ({node.name})")
        
        task_type = node.config.get("task_type", "generic")
        adapter_name = node.config.get("adapter")
        
        if adapter_name and self.orchestrator.adapters:
            adapter = self.orchestrator.adapters.get(adapter_name)
            if adapter:
                try:
                    result = await adapter.execute(
                        action=node.config.get("action"),
                        params=node.config.get("params", {}),
                        context={
                            **context,
                            "process_variables": process_instance.variables,
                            "node_config": node.config
                        }
                    )
                    return result
                except Exception as e:
                    logger.error(f"适配器执行失败: {e}")
                    raise
        
        return {"task_type": task_type, "status": "completed"}


class ConditionNodeHandler(NodeHandler):
    """条件节点处理器"""
    
    async def execute(
        self,
        node: Node,
        node_instance: NodeInstance,
        process_instance: ProcessInstance,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        logger.info(f"执行条件节点: {node.id}")
        
        conditions = node.config.get("conditions", [])
        variables = {**process_instance.variables, **context}
        
        for condition in conditions:
            expr = condition.get("expression", "")
            target = condition.get("target")
            
            try:
                if self._evaluate_condition(expr, variables):
                    return {
                        "condition_met": True,
                        "next_node": target,
                        "expression": expr
                    }
            except Exception as e:
                logger.error(f"条件评估失败: {e}")
        
        default_target = node.config.get("default_target")
        return {
            "condition_met": False,
            "next_node": default_target,
            "used_default": True
        }
    
    def _evaluate_condition(self, expression: str, variables: Dict[str, Any]) -> bool:
        """评估条件表达式"""
        try:
            safe_vars = {
                **variables,
                "true": True,
                "false": False,
                "None": None
            }
            result = eval(expression, {"__builtins__": {}}, safe_vars)
            return bool(result)
        except Exception as e:
            logger.error(f"条件表达式执行错误: {e}")
            return False


class ParallelNodeHandler(NodeHandler):
    """并行网关处理器"""
    
    async def execute(
        self,
        node: Node,
        node_instance: NodeInstance,
        process_instance: ProcessInstance,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        logger.info(f"执行并行网关: {node.id}")
        
        outgoing_edges = self.orchestrator.process_model.get_outgoing_edges(node.id)
        parallel_branches = [edge.target for edge in outgoing_edges]
        
        return {
            "parallel_branches": parallel_branches,
            "branch_count": len(parallel_branches)
        }


class ParallelJoinNodeHandler(NodeHandler):
    """并行汇聚处理器"""
    
    async def execute(
        self,
        node: Node,
        node_instance: NodeInstance,
        process_instance: ProcessInstance,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        logger.info(f"执行并行汇聚: {node.id}")
        
        incoming_edges = self.orchestrator.process_model.get_incoming_edges(node.id)
        completed_branches = []
        
        for edge in incoming_edges:
            source_instance = process_instance.get_node_instance(edge.source)
            if source_instance and source_instance.status == NodeStatus.COMPLETED:
                completed_branches.append(edge.source)
        
        all_completed = len(completed_branches) == len(incoming_edges)
        
        return {
            "all_completed": all_completed,
            "completed_branches": completed_branches,
            "total_branches": len(incoming_edges)
        }


class WaitNodeHandler(NodeHandler):
    """等待节点处理器"""
    
    async def execute(
        self,
        node: Node,
        node_instance: NodeInstance,
        process_instance: ProcessInstance,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        logger.info(f"执行等待节点: {node.id}")
        
        wait_type = node.config.get("wait_type", "duration")
        duration = node.config.get("duration", 0)
        event_name = node.config.get("event_name")
        
        if wait_type == "duration" and duration > 0:
            logger.info(f"等待 {duration} 秒...")
            await asyncio.sleep(duration)
            return {"waited": duration, "wait_type": "duration"}
        
        elif wait_type == "event" and event_name:
            return {
                "wait_type": "event",
                "event_name": event_name,
                "status": "waiting"
            }
        
        return {"status": "skipped"}


class ProcessOrchestrator:
    """流程编排器"""
    
    def __init__(
        self,
        process_model: ProcessModel,
        event_bus: Optional[EventBus] = None,
        monitoring: Optional[MonitoringSystem] = None,
        adapters: Optional[Dict[str, Any]] = None
    ):
        self.process_model = process_model
        self.event_bus = event_bus
        self.monitoring = monitoring
        self.adapters = adapters or {}
        
        self._node_handlers: Dict[NodeType, NodeHandler] = {
            NodeType.START: StartNodeHandler(self),
            NodeType.END: EndNodeHandler(self),
            NodeType.TASK: TaskNodeHandler(self),
            NodeType.CONDITION: ConditionNodeHandler(self),
            NodeType.PARALLEL: ParallelNodeHandler(self),
            NodeType.PARALLEL_JOIN: ParallelJoinNodeHandler(self),
            NodeType.WAIT: WaitNodeHandler(self),
        }
        
        self._process_instances: Dict[str, ProcessInstance] = {}
        self._running_tasks: Dict[str, asyncio.Task] = {}
    
    def create_process_instance(
        self,
        variables: Optional[Dict[str, Any]] = None,
        parent_instance_id: Optional[str] = None
    ) -> ProcessInstance:
        """创建流程实例"""
        instance_id = f"pi_{uuid.uuid4().hex[:12]}"
        
        instance = ProcessInstance(
            id=instance_id,
            process_model_id=self.process_model.id,
            variables=variables or {},
            parent_instance_id=parent_instance_id
        )
        
        self._process_instances[instance_id] = instance
        
        logger.info(f"创建流程实例: {instance_id}")
        
        if self.event_bus:
            asyncio.create_task(self.event_bus.publish(Event(
                event_type="process.created",
                data=instance.to_dict()
            )))
        
        if self.monitoring:
            self.monitoring.increment_counter(MetricType.PROCESS_STARTED)
        
        return instance
    
    async def start_process(
        self,
        variables: Optional[Dict[str, Any]] = None,
        parent_instance_id: Optional[str] = None
    ) -> ProcessInstance:
        """启动流程"""
        instance = self.create_process_instance(variables, parent_instance_id)
        
        start_node = self.process_model.get_start_node()
        if not start_node:
            raise ValueError("流程模型没有开始节点")
        
        instance.status = ProcessStatus.RUNNING
        instance.start_time = datetime.now()
        instance.current_node_ids = [start_node.id]
        
        logger.info(f"启动流程实例: {instance.id}")
        
        if self.event_bus:
            await self.event_bus.publish(Event(
                event_type="process.started",
                data=instance.to_dict()
            ))
        
        task = asyncio.create_task(self._execute_process(instance))
        self._running_tasks[instance.id] = task
        
        return instance
    
    async def _execute_process(self, instance: ProcessInstance):
        """执行流程"""
        try:
            while instance.status == ProcessStatus.RUNNING:
                next_nodes = await self._execute_current_nodes(instance)
                
                if not next_nodes:
                    instance.status = ProcessStatus.COMPLETED
                    instance.end_time = datetime.now()
                    logger.info(f"流程实例完成: {instance.id}")
                    
                    if self.event_bus:
                        await self.event_bus.publish(Event(
                            event_type="process.completed",
                            data=instance.to_dict()
                        ))
                    
                    if self.monitoring:
                        self.monitoring.increment_counter(MetricType.PROCESS_COMPLETED)
                    break
                
                instance.current_node_ids = next_nodes
                instance.updated_at = datetime.now()
        
        except Exception as e:
            instance.status = ProcessStatus.FAILED
            instance.error = str(e)
            instance.end_time = datetime.now()
            logger.error(f"流程实例执行失败: {instance.id}, 错误: {e}")
            
            if self.event_bus:
                await self.event_bus.publish(Event(
                    event_type="process.failed",
                    data={**instance.to_dict(), "error": str(e)}
                ))
            
            if self.monitoring:
                self.monitoring.increment_counter(MetricType.PROCESS_FAILED)
    
    async def _execute_current_nodes(self, instance: ProcessInstance) -> List[str]:
        """执行当前节点"""
        next_nodes = []
        
        for node_id in instance.current_node_ids:
            node = self.process_model.get_node(node_id)
            if not node:
                logger.warning(f"节点不存在: {node_id}")
                continue
            
            node_instance = instance.get_node_instance(node_id)
            if not node_instance:
                node_instance = instance.create_node_instance(node_id)
            
            if node_instance.status == NodeStatus.COMPLETED:
                outgoing = self.process_model.get_outgoing_edges(node_id)
                for edge in outgoing:
                    if edge.target not in next_nodes:
                        next_nodes.append(edge.target)
                continue
            
            try:
                node_instance.status = NodeStatus.RUNNING
                node_instance.start_time = datetime.now()
                
                handler = self._node_handlers.get(node.type)
                if not handler:
                    logger.warning(f"没有找到节点处理器: {node.type}")
                    node_instance.status = NodeStatus.COMPLETED
                    continue
                
                context = {
                    "process_instance_id": instance.id,
                    "node_id": node_id,
                    "timestamp": datetime.now().isoformat()
                }
                
                result = await handler.execute(node, node_instance, instance, context)
                node_instance.output_data = result
                node_instance.status = NodeStatus.COMPLETED
                node_instance.end_time = datetime.now()
                
                logger.info(f"节点执行完成: {node_id}, 结果: {result}")
                
                if self.event_bus:
                    await self.event_bus.publish(Event(
                        event_type="node.completed",
                        data={
                            "process_instance_id": instance.id,
                            "node_id": node_id,
                            "node_instance": node_instance.to_dict()
                        }
                    ))
                
                if self.monitoring:
                    self.monitoring.increment_counter(MetricType.NODE_EXECUTED)
                
                next_nodes.extend(self._get_next_nodes(node, result, instance))
            
            except Exception as e:
                node_instance.status = NodeStatus.FAILED
                node_instance.error = str(e)
                node_instance.end_time = datetime.now()
                
                logger.error(f"节点执行失败: {node_id}, 错误: {e}")
                
                if self.event_bus:
                    await self.event_bus.publish(Event(
                        event_type="node.failed",
                        data={
                            "process_instance_id": instance.id,
                            "node_id": node_id,
                            "error": str(e)
                        }
                    ))
                
                if self.monitoring:
                    self.monitoring.increment_counter(MetricType.NODE_FAILED)
                
                if node_instance.retry_count < node_instance.max_retries:
                    node_instance.retry_count += 1
                    logger.info(f"节点重试: {node_id}, 第 {node_instance.retry_count} 次")
                    instance.current_node_ids = [node_id]
                    return [node_id]
                
                raise
        
        return list(set(next_nodes))
    
    def _get_next_nodes(
        self,
        node: Node,
        result: Dict[str, Any],
        instance: ProcessInstance
    ) -> List[str]:
        """获取下一个节点"""
        next_nodes = []
        
        if node.type == NodeType.CONDITION:
            next_node = result.get("next_node")
            if next_node:
                next_nodes.append(next_node)
        
        elif node.type == NodeType.PARALLEL:
            parallel_branches = result.get("parallel_branches", [])
            next_nodes.extend(parallel_branches)
        
        elif node.type == NodeType.PARALLEL_JOIN:
            if result.get("all_completed"):
                outgoing = self.process_model.get_outgoing_edges(node.id)
                for edge in outgoing:
                    next_nodes.append(edge.target)
        
        elif node.type == NodeType.END:
            pass
        
        else:
            outgoing = self.process_model.get_outgoing_edges(node.id)
            for edge in outgoing:
                if edge.condition:
                    try:
                        variables = {**instance.variables, **result}
                        if self._evaluate_edge_condition(edge.condition, variables):
                            next_nodes.append(edge.target)
                    except Exception as e:
                        logger.error(f"边条件评估失败: {e}")
                else:
                    next_nodes.append(edge.target)
        
        return next_nodes
    
    def _evaluate_edge_condition(self, condition: str, variables: Dict[str, Any]) -> bool:
        """评估边的条件"""
        try:
            safe_vars = {
                **variables,
                "true": True,
                "false": False,
                "None": None
            }
            result = eval(condition, {"__builtins__": {}}, safe_vars)
            return bool(result)
        except Exception as e:
            logger.error(f"边条件表达式执行错误: {e}")
            return False
    
    def get_process_instance(self, instance_id: str) -> Optional[ProcessInstance]:
        """获取流程实例"""
        return self._process_instances.get(instance_id)
    
    def cancel_process(self, instance_id: str) -> bool:
        """取消流程"""
        instance = self._process_instances.get(instance_id)
        if not instance:
            return False
        
        if instance.status in [ProcessStatus.RUNNING, ProcessStatus.PENDING]:
            instance.status = ProcessStatus.CANCELLED
            instance.end_time = datetime.now()
            
            task = self._running_tasks.pop(instance_id, None)
            if task:
                task.cancel()
            
            logger.info(f"流程实例已取消: {instance_id}")
            return True
        
        return False
    
    async def wait_for_completion(self, instance_id: str, timeout: Optional[float] = None) -> ProcessInstance:
        """等待流程完成"""
        instance = self._process_instances.get(instance_id)
        if not instance:
            raise ValueError(f"流程实例不存在: {instance_id}")
        
        task = self._running_tasks.get(instance_id)
        if task:
            try:
                await asyncio.wait_for(task, timeout=timeout)
            except asyncio.TimeoutError:
                logger.warning(f"等待流程超时: {instance_id}")
                raise
        
        return instance
