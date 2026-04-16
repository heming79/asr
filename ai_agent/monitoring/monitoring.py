"""
全链路实时监控系统
支持指标收集、链路追踪、告警管理
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, Any, Optional, List, Callable
from collections import defaultdict, deque

logger = logging.getLogger(__name__)


class MetricType(Enum):
    """指标类型"""
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    TIMER = "timer"
    
    PROCESS_STARTED = "process_started"
    PROCESS_COMPLETED = "process_completed"
    PROCESS_FAILED = "process_failed"
    NODE_EXECUTED = "node_executed"
    NODE_FAILED = "node_failed"
    API_CALL = "api_call"
    API_ERROR = "api_error"
    EVENT_PUBLISHED = "event_published"
    EVENT_CONSUMED = "event_consumed"


class AlertLevel(Enum):
    """告警级别"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class Metric:
    """指标数据"""
    name: str
    type: MetricType
    value: float
    labels: Dict[str, str] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "type": self.type.value,
            "value": self.value,
            "labels": self.labels,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata
        }


@dataclass
class Alert:
    """告警"""
    alert_id: str
    name: str
    level: AlertLevel
    message: str
    source: str
    timestamp: datetime = field(default_factory=datetime.now)
    resolved: bool = False
    resolved_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "alert_id": self.alert_id,
            "name": self.name,
            "level": self.level.value,
            "message": self.message,
            "source": self.source,
            "timestamp": self.timestamp.isoformat(),
            "resolved": self.resolved,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "metadata": self.metadata
        }


@dataclass
class TraceSpan:
    """追踪跨度"""
    span_id: str
    trace_id: str
    parent_span_id: Optional[str]
    name: str
    service: str
    start_time: datetime
    end_time: Optional[datetime] = None
    duration_ms: Optional[float] = None
    status: str = "running"
    attributes: Dict[str, Any] = field(default_factory=dict)
    events: List[Dict[str, Any]] = field(default_factory=list)
    
    def end(self, status: str = "completed"):
        """结束跨度"""
        self.end_time = datetime.now()
        self.duration_ms = (self.end_time - self.start_time).total_seconds() * 1000
        self.status = status
    
    def add_event(self, name: str, attributes: Optional[Dict[str, Any]] = None):
        """添加事件"""
        self.events.append({
            "name": name,
            "timestamp": datetime.now().isoformat(),
            "attributes": attributes or {}
        })
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "span_id": self.span_id,
            "trace_id": self.trace_id,
            "parent_span_id": self.parent_span_id,
            "name": self.name,
            "service": self.service,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_ms": self.duration_ms,
            "status": self.status,
            "attributes": self.attributes,
            "events": self.events
        }


@dataclass
class Trace:
    """追踪"""
    trace_id: str
    name: str
    start_time: datetime = field(default_factory=datetime.now)
    end_time: Optional[datetime] = None
    spans: Dict[str, TraceSpan] = field(default_factory=dict)
    status: str = "running"
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def create_span(
        self,
        name: str,
        service: str,
        parent_span_id: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None
    ) -> TraceSpan:
        """创建跨度"""
        span_id = uuid.uuid4().hex[:16]
        span = TraceSpan(
            span_id=span_id,
            trace_id=self.trace_id,
            parent_span_id=parent_span_id,
            name=name,
            service=service,
            start_time=datetime.now(),
            attributes=attributes or {}
        )
        self.spans[span_id] = span
        return span
    
    def end(self, status: str = "completed"):
        """结束追踪"""
        self.end_time = datetime.now()
        self.status = status
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "name": self.name,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "spans": {k: v.to_dict() for k, v in self.spans.items()},
            "status": self.status,
            "metadata": self.metadata
        }


class MonitoringSystem:
    """监控系统"""
    
    def __init__(self, max_metrics: int = 10000, max_alerts: int = 1000, max_traces: int = 1000):
        self._metrics: deque = deque(maxlen=max_metrics)
        self._counters: Dict[str, int] = defaultdict(int)
        self._gauges: Dict[str, float] = {}
        self._histograms: Dict[str, List[float]] = defaultdict(list)
        
        self._alerts: deque = deque(maxlen=max_alerts)
        self._active_alerts: Dict[str, Alert] = {}
        
        self._traces: Dict[str, Trace] = {}
        self._trace_history: deque = deque(maxlen=max_traces)
        
        self._alert_handlers: List[Callable[[Alert], None]] = []
        self._running = False
        self._cleanup_task: Optional[asyncio.Task] = None
    
    def start(self):
        """启动监控系统"""
        if self._running:
            return
        self._running = True
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("监控系统已启动")
    
    async def stop(self):
        """停止监控系统"""
        self._running = False
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        logger.info("监控系统已停止")
    
    async def _cleanup_loop(self):
        """清理循环"""
        while self._running:
            try:
                await asyncio.sleep(60)
                self._cleanup_old_traces()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"监控清理循环错误: {e}")
    
    def _cleanup_old_traces(self):
        """清理旧的追踪数据"""
        cutoff = datetime.now() - timedelta(hours=24)
        to_remove = [
            trace_id for trace_id, trace in self._traces.items()
            if trace.end_time and trace.end_time < cutoff
        ]
        for trace_id in to_remove:
            trace = self._traces.pop(trace_id)
            self._trace_history.append(trace)
    
    def record_metric(
        self,
        name: str,
        metric_type: MetricType,
        value: float = 1.0,
        labels: Optional[Dict[str, str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """记录指标"""
        metric = Metric(
            name=name,
            type=metric_type,
            value=value,
            labels=labels or {},
            metadata=metadata or {}
        )
        self._metrics.append(metric)
        
        if metric_type == MetricType.COUNTER:
            self._counters[name] += value
        elif metric_type == MetricType.GAUGE:
            self._gauges[name] = value
        elif metric_type in [MetricType.HISTOGRAM, MetricType.TIMER]:
            self._histograms[name].append(value)
            if len(self._histograms[name]) > 1000:
                self._histograms[name] = self._histograms[name][-500:]
        
        logger.debug(f"记录指标: {name} = {value}")
    
    def increment_counter(self, metric_type: MetricType, labels: Optional[Dict[str, str]] = None):
        """递增计数器"""
        self.record_metric(metric_type.value, MetricType.COUNTER, 1.0, labels)
    
    def set_gauge(self, name: str, value: float, labels: Optional[Dict[str, str]] = None):
        """设置仪表盘值"""
        self.record_metric(name, MetricType.GAUGE, value, labels)
    
    def record_timer(self, name: str, duration_ms: float, labels: Optional[Dict[str, str]] = None):
        """记录计时器"""
        self.record_metric(name, MetricType.TIMER, duration_ms, labels)
    
    def get_counter(self, name: str) -> int:
        """获取计数器值"""
        return self._counters.get(name, 0)
    
    def get_gauge(self, name: str) -> Optional[float]:
        """获取仪表盘值"""
        return self._gauges.get(name)
    
    def get_histogram_stats(self, name: str) -> Dict[str, float]:
        """获取直方图统计"""
        values = self._histograms.get(name, [])
        if not values:
            return {"count": 0, "min": 0, "max": 0, "avg": 0, "p50": 0, "p95": 0, "p99": 0}
        
        sorted_values = sorted(values)
        n = len(sorted_values)
        
        def percentile(p):
            idx = int(n * p / 100)
            return sorted_values[min(idx, n - 1)]
        
        return {
            "count": n,
            "min": min(values),
            "max": max(values),
            "avg": sum(values) / n,
            "p50": percentile(50),
            "p95": percentile(95),
            "p99": percentile(99)
        }
    
    def create_alert(
        self,
        name: str,
        level: AlertLevel,
        message: str,
        source: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Alert:
        """创建告警"""
        alert_id = uuid.uuid4().hex
        alert = Alert(
            alert_id=alert_id,
            name=name,
            level=level,
            message=message,
            source=source,
            metadata=metadata or {}
        )
        
        self._alerts.append(alert)
        self._active_alerts[alert_id] = alert
        
        logger.warning(f"创建告警 [{level.value}]: {name} - {message}")
        
        for handler in self._alert_handlers:
            try:
                handler(alert)
            except Exception as e:
                logger.error(f"告警处理器执行失败: {e}")
        
        return alert
    
    def resolve_alert(self, alert_id: str) -> bool:
        """解决告警"""
        alert = self._active_alerts.pop(alert_id, None)
        if alert:
            alert.resolved = True
            alert.resolved_at = datetime.now()
            logger.info(f"告警已解决: {alert_id}")
            return True
        return False
    
    def get_active_alerts(self, level: Optional[AlertLevel] = None) -> List[Alert]:
        """获取活跃告警"""
        alerts = list(self._active_alerts.values())
        if level:
            alerts = [a for a in alerts if a.level == level]
        return alerts
    
    def get_alert_history(self, limit: int = 100) -> List[Alert]:
        """获取告警历史"""
        return list(self._alerts)[-limit:]
    
    def add_alert_handler(self, handler: Callable[[Alert], None]):
        """添加告警处理器"""
        self._alert_handlers.append(handler)
    
    def start_trace(self, name: str, metadata: Optional[Dict[str, Any]] = None) -> Trace:
        """开始追踪"""
        trace_id = uuid.uuid4().hex
        trace = Trace(
            trace_id=trace_id,
            name=name,
            metadata=metadata or {}
        )
        self._traces[trace_id] = trace
        logger.debug(f"开始追踪: {name} ({trace_id})")
        return trace
    
    def get_trace(self, trace_id: str) -> Optional[Trace]:
        """获取追踪"""
        return self._traces.get(trace_id)
    
    def end_trace(self, trace_id: str, status: str = "completed") -> bool:
        """结束追踪"""
        trace = self._traces.get(trace_id)
        if trace:
            trace.end(status)
            logger.debug(f"结束追踪: {trace_id}")
            return True
        return False
    
    def get_recent_traces(self, limit: int = 100) -> List[Trace]:
        """获取最近的追踪"""
        traces = list(self._traces.values())
        traces.sort(key=lambda t: t.start_time, reverse=True)
        return traces[:limit]
    
    def get_metrics_summary(self) -> Dict[str, Any]:
        """获取指标摘要"""
        return {
            "counters": dict(self._counters),
            "gauges": dict(self._gauges),
            "histograms": {
                name: self.get_histogram_stats(name)
                for name in self._histograms
            },
            "total_metrics_recorded": len(self._metrics)
        }
    
    def get_health_status(self) -> Dict[str, Any]:
        """获取健康状态"""
        active_alerts = self.get_active_alerts()
        critical_alerts = [a for a in active_alerts if a.level == AlertLevel.CRITICAL]
        error_alerts = [a for a in active_alerts if a.level == AlertLevel.ERROR]
        
        status = "healthy"
        if critical_alerts:
            status = "critical"
        elif error_alerts:
            status = "degraded"
        
        return {
            "status": status,
            "active_alerts_count": len(active_alerts),
            "critical_alerts_count": len(critical_alerts),
            "error_alerts_count": len(error_alerts),
            "active_traces_count": len(self._traces),
            "timestamp": datetime.now().isoformat()
        }
