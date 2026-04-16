"""
适配器基类
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class AdapterResult:
    """适配器执行结果"""
    success: bool
    data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat()
        }


class BaseAdapter(ABC):
    """适配器基类"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.base_url = config.get("base_url", "")
        self.api_key = config.get("api_key", "")
        self.timeout = config.get("timeout", 30)
        self.max_retries = config.get("max_retries", 3)
        self.retry_delay = config.get("retry_delay", 1)
    
    @abstractmethod
    async def execute(
        self,
        action: str,
        params: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> AdapterResult:
        """执行适配器操作"""
        pass
    
    @abstractmethod
    async def health_check(self) -> bool:
        """健康检查"""
        pass
    
    def _build_url(self, endpoint: str) -> str:
        """构建完整URL"""
        if self.base_url.endswith("/") and endpoint.startswith("/"):
            return self.base_url + endpoint[1:]
        elif not self.base_url.endswith("/") and not endpoint.startswith("/"):
            return f"{self.base_url}/{endpoint}"
        return self.base_url + endpoint
    
    def _get_headers(self) -> Dict[str, str]:
        """获取请求头"""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers
