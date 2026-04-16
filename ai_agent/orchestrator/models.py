"""
流程模型定义
包含流程、节点、边等核心数据结构
"""

import uuid
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any, Callable
from abc import ABC, abstractmethod


class NodeType(Enum):
    """节点类型"""
    START = "start"
    END = "end"
    TASK = "task"
    CONDITION = "condition"
    PARALLEL = "parallel"
    PARALLEL_JOIN = "parallel_join"
    SUBPROCESS = "subprocess"
    WAIT = "wait"
    EVENT = "event"


class ProcessStatus(Enum):
    """流程状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SUSPENDED = "suspended"


class NodeStatus(Enum):
    """节点状态"""
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class Node:
    """流程节点"""
    id: str
    name: str
    type: NodeType
    config: Dict[str, Any] = field(default_factory=dict)
    description: str = ""
    position: Dict[str, float] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type.value,
            "config": self.config,
            "description": self.description,
            "position": self.position,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Node':
        return cls(
            id=data["id"],
            name=data["name"],
            type=NodeType(data["type"]),
            config=data.get("config", {}),
            description=data.get("description", ""),
            position=data.get("position", {}),
            metadata=data.get("metadata", {})
        )


@dataclass
class Edge:
    """流程边（连接节点）"""
    id: str
    source: str
    target: str
    condition: Optional[str] = None
    label: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "source": self.source,
            "target": self.target,
            "condition": self.condition,
            "label": self.label,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Edge':
        return cls(
            id=data["id"],
            source=data["source"],
            target=data["target"],
            condition=data.get("condition"),
            label=data.get("label", ""),
            metadata=data.get("metadata", {})
        )


@dataclass
class ProcessModel:
    """流程模型定义"""
    id: str
    name: str
    version: str = "1.0.0"
    description: str = ""
    nodes: List[Node] = field(default_factory=list)
    edges: List[Edge] = field(default_factory=list)
    variables: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    
    def get_start_node(self) -> Optional[Node]:
        """获取开始节点"""
        for node in self.nodes:
            if node.type == NodeType.START:
                return node
        return None
    
    def get_end_nodes(self) -> List[Node]:
        """获取结束节点"""
        return [node for node in self.nodes if node.type == NodeType.END]
    
    def get_node(self, node_id: str) -> Optional[Node]:
        """根据ID获取节点"""
        for node in self.nodes:
            if node.id == node_id:
                return node
        return None
    
    def get_outgoing_edges(self, node_id: str) -> List[Edge]:
        """获取节点的出边"""
        return [edge for edge in self.edges if edge.source == node_id]
    
    def get_incoming_edges(self, node_id: str) -> List[Edge]:
        """获取节点的入边"""
        return [edge for edge in self.edges if edge.target == node_id]
    
    def validate(self) -> List[str]:
        """验证流程模型的有效性"""
        errors = []
        
        start_nodes = [n for n in self.nodes if n.type == NodeType.START]
        if len(start_nodes) == 0:
            errors.append("流程必须包含一个开始节点")
        elif len(start_nodes) > 1:
            errors.append("流程只能包含一个开始节点")
        
        end_nodes = [n for n in self.nodes if n.type == NodeType.END]
        if len(end_nodes) == 0:
            errors.append("流程必须包含至少一个结束节点")
        
        node_ids = {node.id for node in self.nodes}
        for edge in self.edges:
            if edge.source not in node_ids:
                errors.append(f"边 {edge.id} 的源节点 {edge.source} 不存在")
            if edge.target not in node_ids:
                errors.append(f"边 {edge.id} 的目标节点 {edge.target} 不存在")
        
        for node in self.nodes:
            if node.type not in [NodeType.START, NodeType.END]:
                outgoing = self.get_outgoing_edges(node.id)
                incoming = self.get_incoming_edges(node.id)
                if len(outgoing) == 0 and node.type != NodeType.END:
                    errors.append(f"节点 {node.id} ({node.name}) 没有出边")
                if len(incoming) == 0 and node.type != NodeType.START:
                    errors.append(f"节点 {node.id} ({node.name}) 没有入边")
        
        return errors
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": [edge.to_dict() for edge in self.edges],
            "variables": self.variables,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ProcessModel':
        return cls(
            id=data["id"],
            name=data["name"],
            version=data.get("version", "1.0.0"),
            description=data.get("description", ""),
            nodes=[Node.from_dict(n) for n in data.get("nodes", [])],
            edges=[Edge.from_dict(e) for e in data.get("edges", [])],
            variables=data.get("variables", {}),
            metadata=data.get("metadata", {}),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(),
            updated_at=datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else datetime.now()
        )
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)
    
    @classmethod
    def from_json(cls, json_str: str) -> 'ProcessModel':
        return cls.from_dict(json.loads(json_str))


@dataclass
class NodeInstance:
    """节点执行实例"""
    id: str
    node_id: str
    process_instance_id: str
    status: NodeStatus = NodeStatus.PENDING
    input_data: Dict[str, Any] = field(default_factory=dict)
    output_data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    retry_count: int = 0
    max_retries: int = 3
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "node_id": self.node_id,
            "process_instance_id": self.process_instance_id,
            "status": self.status.value,
            "input_data": self.input_data,
            "output_data": self.output_data,
            "error": self.error,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "metadata": self.metadata
        }


@dataclass
class ProcessInstance:
    """流程执行实例"""
    id: str
    process_model_id: str
    status: ProcessStatus = ProcessStatus.PENDING
    variables: Dict[str, Any] = field(default_factory=dict)
    node_instances: Dict[str, NodeInstance] = field(default_factory=dict)
    current_node_ids: List[str] = field(default_factory=list)
    parent_instance_id: Optional[str] = None
    error: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def get_node_instance(self, node_id: str) -> Optional[NodeInstance]:
        return self.node_instances.get(node_id)
    
    def create_node_instance(self, node_id: str) -> NodeInstance:
        instance_id = f"ni_{uuid.uuid4().hex[:12]}"
        node_instance = NodeInstance(
            id=instance_id,
            node_id=node_id,
            process_instance_id=self.id
        )
        self.node_instances[node_id] = node_instance
        return node_instance
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "process_model_id": self.process_model_id,
            "status": self.status.value,
            "variables": self.variables,
            "node_instances": {k: v.to_dict() for k, v in self.node_instances.items()},
            "current_node_ids": self.current_node_ids,
            "parent_instance_id": self.parent_instance_id,
            "error": self.error,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "metadata": self.metadata
        }
