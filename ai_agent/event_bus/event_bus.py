"""
事件总线实现
支持事件发布、订阅和异步处理
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, Any, Optional, List, Callable, Awaitable
from collections import defaultdict

logger = logging.getLogger(__name__)


class EventPriority(Enum):
    """事件优先级"""
    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


@dataclass
class Event:
    """事件对象"""
    event_type: str
    data: Dict[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    timestamp: datetime = field(default_factory=datetime.now)
    source: Optional[str] = None
    priority: EventPriority = EventPriority.NORMAL
    correlation_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "data": self.data,
            "timestamp": self.timestamp.isoformat(),
            "source": self.source,
            "priority": self.priority.value,
            "correlation_id": self.correlation_id,
            "metadata": self.metadata
        }


class EventHandler:
    """事件处理器"""
    
    def __init__(
        self,
        handler: Callable[[Event], Awaitable[None]],
        event_type: str,
        priority: EventPriority = EventPriority.NORMAL,
        filter_func: Optional[Callable[[Event], bool]] = None
    ):
        self.handler = handler
        self.event_type = event_type
        self.priority = priority
        self.filter_func = filter_func
        self.handler_id = uuid.uuid4().hex
    
    async def handle(self, event: Event) -> bool:
        """处理事件"""
        try:
            if self.filter_func and not self.filter_func(event):
                return True
            
            await self.handler(event)
            return True
        except Exception as e:
            logger.error(f"事件处理器执行失败: {self.handler_id}, 错误: {e}")
            return False


class EventBus:
    """事件总线"""
    
    def __init__(self, max_queue_size: int = 10000):
        self._subscribers: Dict[str, List[EventHandler]] = defaultdict(list)
        self._event_queue: asyncio.Queue = asyncio.Queue(maxsize=max_queue_size)
        self._running = False
        self._worker_tasks: List[asyncio.Task] = []
        self._event_history: List[Event] = []
        self._max_history_size = 10000
    
    def subscribe(
        self,
        event_type: str,
        handler: Callable[[Event], Awaitable[None]],
        priority: EventPriority = EventPriority.NORMAL,
        filter_func: Optional[Callable[[Event], bool]] = None
    ) -> str:
        """订阅事件"""
        event_handler = EventHandler(handler, event_type, priority, filter_func)
        self._subscribers[event_type].append(event_handler)
        
        self._subscribers[event_type].sort(key=lambda h: h.priority.value, reverse=True)
        
        logger.info(f"订阅事件: {event_type}, 处理器ID: {event_handler.handler_id}")
        return event_handler.handler_id
    
    def unsubscribe(self, handler_id: str) -> bool:
        """取消订阅"""
        for event_type, handlers in self._subscribers.items():
            for i, handler in enumerate(handlers):
                if handler.handler_id == handler_id:
                    handlers.pop(i)
                    logger.info(f"取消订阅: {handler_id}")
                    return True
        return False
    
    async def publish(self, event: Event) -> bool:
        """发布事件"""
        try:
            await self._event_queue.put(event)
            logger.debug(f"事件已发布: {event.event_type} ({event.event_id})")
            return True
        except asyncio.QueueFull:
            logger.warning(f"事件队列已满，丢弃事件: {event.event_type}")
            return False
    
    async def publish_nowait(self, event: Event) -> bool:
        """非阻塞发布事件"""
        try:
            self._event_queue.put_nowait(event)
            logger.debug(f"事件已发布(非阻塞): {event.event_type} ({event.event_id})")
            return True
        except asyncio.QueueFull:
            logger.warning(f"事件队列已满，丢弃事件: {event.event_type}")
            return False
    
    async def _process_event(self, event: Event):
        """处理单个事件"""
        self._event_history.append(event)
        if len(self._event_history) > self._max_history_size:
            self._event_history = self._event_history[-self._max_history_size // 2:]
        
        handlers = self._subscribers.get(event.event_type, [])
        
        wildcard_handlers = self._subscribers.get("*", [])
        all_handlers = handlers + wildcard_handlers
        
        all_handlers.sort(key=lambda h: h.priority.value, reverse=True)
        
        if not all_handlers:
            logger.debug(f"没有处理器处理事件: {event.event_type}")
            return
        
        tasks = []
        for handler in all_handlers:
            task = asyncio.create_task(handler.handle(event))
            tasks.append(task)
        
        await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _worker(self):
        """工作协程"""
        while self._running:
            try:
                event = await asyncio.wait_for(
                    self._event_queue.get(),
                    timeout=1.0
                )
                await self._process_event(event)
                self._event_queue.task_done()
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"事件处理工作协程错误: {e}")
    
    def start(self, worker_count: int = 3):
        """启动事件总线"""
        if self._running:
            return
        
        self._running = True
        for i in range(worker_count):
            task = asyncio.create_task(self._worker())
            self._worker_tasks.append(task)
        
        logger.info(f"事件总线已启动，工作协程数: {worker_count}")
    
    async def stop(self):
        """停止事件总线"""
        self._running = False
        
        for task in self._worker_tasks:
            task.cancel()
        
        if self._worker_tasks:
            await asyncio.gather(*self._worker_tasks, return_exceptions=True)
        
        self._worker_tasks = []
        logger.info("事件总线已停止")
    
    def get_event_history(
        self,
        event_type: Optional[str] = None,
        limit: int = 100
    ) -> List[Event]:
        """获取事件历史"""
        history = self._event_history
        
        if event_type:
            history = [e for e in history if e.event_type == event_type]
        
        return history[-limit:]
    
    def get_subscriber_count(self, event_type: Optional[str] = None) -> int:
        """获取订阅者数量"""
        if event_type:
            return len(self._subscribers.get(event_type, []))
        
        total = 0
        for handlers in self._subscribers.values():
            total += len(handlers)
        return total
    
    def get_queue_size(self) -> int:
        """获取队列大小"""
        return self._event_queue.qsize()
