"""
系统适配器模块
"""

from .base import BaseAdapter, AdapterResult
from .oms_adapter import OMSAdapter
from .wms_adapter import WMSAdapter
from .tms_adapter import TMSAdapter

__all__ = [
    "BaseAdapter",
    "AdapterResult",
    "OMSAdapter",
    "WMSAdapter",
    "TMSAdapter"
]
