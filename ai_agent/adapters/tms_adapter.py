"""
TMS (运输管理系统) 适配器
负责与运输管理系统进行交互
"""

import logging
import aiohttp
from typing import Dict, Any, Optional, List
from datetime import datetime

from .base import BaseAdapter, AdapterResult

logger = logging.getLogger(__name__)


class TMSAdapter(BaseAdapter):
    """TMS适配器"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.system_name = "TMS"
    
    async def execute(
        self,
        action: str,
        params: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> AdapterResult:
        """执行TMS操作"""
        logger.info(f"执行TMS操作: {action}, 参数: {params}")
        
        action_handlers = {
            "create_shipment": self._create_shipment,
            "get_shipment": self._get_shipment,
            "assign_carrier": self._assign_carrier,
            "create_delivery_task": self._create_delivery_task,
            "update_shipment_status": self._update_shipment_status,
            "track_shipment": self._track_shipment,
            "confirm_delivery": self._confirm_delivery,
            "get_carriers": self._get_carriers,
            "calculate_shipping_fee": self._calculate_shipping_fee,
        }
        
        handler = action_handlers.get(action)
        if not handler:
            return AdapterResult(
                success=False,
                error=f"未知的TMS操作: {action}"
            )
        
        try:
            return await handler(params, context)
        except Exception as e:
            logger.error(f"TMS操作执行失败: {action}, 错误: {e}")
            return AdapterResult(
                success=False,
                error=str(e),
                metadata={"action": action}
            )
    
    async def _create_shipment(
        self,
        params: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> AdapterResult:
        """创建运单"""
        order_no = params.get("order_no")
        shipping_address = params.get("shipping_address", {})
        packages = params.get("packages", [])
        
        if not order_no or not shipping_address:
            return AdapterResult(
                success=False,
                error="缺少订单号或收货地址"
            )
        
        shipment_no = f"SH{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        if self.base_url:
            url = self._build_url("/api/shipments")
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json={
                        "shipment_no": shipment_no,
                        "order_no": order_no,
                        "shipping_address": shipping_address,
                        "packages": packages,
                        "sender_address": params.get("sender_address", {}),
                        "shipping_type": params.get("shipping_type", "STANDARD")
                    },
                    headers=self._get_headers(),
                    timeout=self.timeout
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        return AdapterResult(
                            success=True,
                            data={
                                "shipment_no": result.get("shipment_no", shipment_no),
                                "order_no": order_no,
                                "status": "CREATED",
                                "created_at": datetime.now().isoformat()
                            }
                        )
        
        return AdapterResult(
            success=True,
            data={
                "shipment_no": shipment_no,
                "order_no": order_no,
                "status": "CREATED",
                "created_at": datetime.now().isoformat(),
                "_mock": True
            }
        )
    
    async def _get_shipment(
        self,
        params: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> AdapterResult:
        """获取运单信息"""
        shipment_no = params.get("shipment_no")
        
        if not shipment_no:
            return AdapterResult(
                success=False,
                error="缺少运单号"
            )
        
        return AdapterResult(
            success=True,
            data={
                "shipment_no": shipment_no,
                "order_no": params.get("order_no", ""),
                "status": params.get("status", "CREATED"),
                "shipping_address": params.get("shipping_address", {}),
                "_mock": True
            }
        )
    
    async def _assign_carrier(
        self,
        params: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> AdapterResult:
        """分配承运商"""
        shipment_no = params.get("shipment_no")
        carrier_code = params.get("carrier_code")
        
        if not shipment_no or not carrier_code:
            return AdapterResult(
                success=False,
                error="缺少运单号或承运商代码"
            )
        
        tracking_no = f"TN{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        return AdapterResult(
            success=True,
            data={
                "shipment_no": shipment_no,
                "carrier_code": carrier_code,
                "carrier_name": params.get("carrier_name", "默认承运商"),
                "tracking_no": tracking_no,
                "assigned_at": datetime.now().isoformat()
            }
        )
    
    async def _create_delivery_task(
        self,
        params: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> AdapterResult:
        """创建配送任务"""
        shipment_no = params.get("shipment_no")
        packages = params.get("packages", [])
        
        if not shipment_no:
            return AdapterResult(
                success=False,
                error="缺少运单号"
            )
        
        delivery_task_no = f"DT{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        return AdapterResult(
            success=True,
            data={
                "delivery_task_no": delivery_task_no,
                "shipment_no": shipment_no,
                "packages": packages,
                "status": "PENDING",
                "created_at": datetime.now().isoformat()
            }
        )
    
    async def _update_shipment_status(
        self,
        params: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> AdapterResult:
        """更新运单状态"""
        shipment_no = params.get("shipment_no")
        status = params.get("status")
        location = params.get("location", "")
        remark = params.get("remark", "")
        
        if not shipment_no or not status:
            return AdapterResult(
                success=False,
                error="缺少运单号或状态"
            )
        
        valid_statuses = [
            "CREATED", "ASSIGNED", "PICKED_UP", "IN_TRANSIT",
            "OUT_FOR_DELIVERY", "DELIVERED", "FAILED", "RETURNED"
        ]
        
        if status not in valid_statuses:
            return AdapterResult(
                success=False,
                error=f"无效的运单状态: {status}"
            )
        
        return AdapterResult(
            success=True,
            data={
                "shipment_no": shipment_no,
                "status": status,
                "location": location,
                "remark": remark,
                "updated_at": datetime.now().isoformat()
            }
        )
    
    async def _track_shipment(
        self,
        params: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> AdapterResult:
        """追踪运单"""
        shipment_no = params.get("shipment_no")
        tracking_no = params.get("tracking_no")
        
        if not shipment_no and not tracking_no:
            return AdapterResult(
                success=False,
                error="缺少运单号或追踪号"
            )
        
        tracking_events = [
            {
                "status": "CREATED",
                "location": "仓库",
                "time": datetime.now().isoformat(),
                "remark": "运单已创建"
            }
        ]
        
        return AdapterResult(
            success=True,
            data={
                "shipment_no": shipment_no,
                "tracking_no": tracking_no,
                "current_status": params.get("current_status", "CREATED"),
                "tracking_events": tracking_events,
                "_mock": True
            }
        )
    
    async def _confirm_delivery(
        self,
        params: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> AdapterResult:
        """确认送达"""
        shipment_no = params.get("shipment_no")
        receiver_name = params.get("receiver_name", "")
        signature = params.get("signature", "")
        
        if not shipment_no:
            return AdapterResult(
                success=False,
                error="缺少运单号"
            )
        
        return AdapterResult(
            success=True,
            data={
                "shipment_no": shipment_no,
                "receiver_name": receiver_name,
                "signature": signature,
                "delivered_at": datetime.now().isoformat()
            }
        )
    
    async def _get_carriers(
        self,
        params: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> AdapterResult:
        """获取可用承运商列表"""
        carriers = [
            {
                "code": "SF",
                "name": "顺丰速运",
                "supported_types": ["STANDARD", "EXPRESS", "NEXT_DAY"],
                "coverage_areas": ["全国"]
            },
            {
                "code": "JD",
                "name": "京东物流",
                "supported_types": ["STANDARD", "EXPRESS"],
                "coverage_areas": ["全国"]
            },
            {
                "code": "ZT",
                "name": "中通快递",
                "supported_types": ["STANDARD"],
                "coverage_areas": ["全国"]
            },
            {
                "code": "YT",
                "name": "圆通速递",
                "supported_types": ["STANDARD"],
                "coverage_areas": ["全国"]
            }
        ]
        
        return AdapterResult(
            success=True,
            data={
                "carriers": carriers,
                "total": len(carriers)
            }
        )
    
    async def _calculate_shipping_fee(
        self,
        params: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> AdapterResult:
        """计算运费"""
        from_address = params.get("from_address", {})
        to_address = params.get("to_address", {})
        weight = params.get("weight", 1.0)
        shipping_type = params.get("shipping_type", "STANDARD")
        
        base_fee = {
            "STANDARD": 10.0,
            "EXPRESS": 15.0,
            "NEXT_DAY": 25.0,
            "SAME_DAY": 35.0
        }
        
        fee = base_fee.get(shipping_type, 10.0)
        if weight > 1.0:
            fee += (weight - 1.0) * 5.0
        
        return AdapterResult(
            success=True,
            data={
                "from_address": from_address,
                "to_address": to_address,
                "weight": weight,
                "shipping_type": shipping_type,
                "shipping_fee": round(fee, 2),
                "currency": "CNY"
            }
        )
    
    async def health_check(self) -> bool:
        """健康检查"""
        if not self.base_url:
            return True
        
        try:
            url = self._build_url("/api/health")
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=5) as response:
                    return response.status == 200
        except Exception as e:
            logger.warning(f"TMS健康检查失败: {e}")
            return False
