"""
OMS (订单管理系统) 适配器
负责与订单管理系统进行交互
"""

import logging
import aiohttp
from typing import Dict, Any, Optional, List
from datetime import datetime

from .base import BaseAdapter, AdapterResult

logger = logging.getLogger(__name__)


class OMSAdapter(BaseAdapter):
    """OMS适配器"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.system_name = "OMS"
    
    async def execute(
        self,
        action: str,
        params: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> AdapterResult:
        """执行OMS操作"""
        logger.info(f"执行OMS操作: {action}, 参数: {params}")
        
        action_handlers = {
            "create_order": self._create_order,
            "get_order": self._get_order,
            "update_order_status": self._update_order_status,
            "cancel_order": self._cancel_order,
            "allocate_inventory": self._allocate_inventory,
            "search_orders": self._search_orders,
            "get_order_items": self._get_order_items,
            "update_order_address": self._update_order_address,
        }
        
        handler = action_handlers.get(action)
        if not handler:
            return AdapterResult(
                success=False,
                error=f"未知的OMS操作: {action}"
            )
        
        try:
            return await handler(params, context)
        except Exception as e:
            logger.error(f"OMS操作执行失败: {action}, 错误: {e}")
            return AdapterResult(
                success=False,
                error=str(e),
                metadata={"action": action}
            )
    
    async def _create_order(
        self,
        params: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> AdapterResult:
        """创建订单"""
        required_fields = ["order_no", "customer_id", "items"]
        for field in required_fields:
            if field not in params:
                return AdapterResult(
                    success=False,
                    error=f"缺少必填字段: {field}"
                )
        
        order_data = {
            "order_no": params["order_no"],
            "customer_id": params["customer_id"],
            "customer_name": params.get("customer_name", ""),
            "items": params["items"],
            "shipping_address": params.get("shipping_address", {}),
            "billing_address": params.get("billing_address", {}),
            "payment_method": params.get("payment_method", ""),
            "total_amount": params.get("total_amount", 0),
            "discount_amount": params.get("discount_amount", 0),
            "shipping_fee": params.get("shipping_fee", 0),
            "remark": params.get("remark", ""),
            "source_channel": params.get("source_channel", "ONLINE"),
        }
        
        if self.base_url:
            url = self._build_url("/api/orders")
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json=order_data,
                    headers=self._get_headers(),
                    timeout=self.timeout
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        return AdapterResult(
                            success=True,
                            data={
                                "order_id": result.get("order_id", params["order_no"]),
                                "order_no": params["order_no"],
                                "status": "CREATED",
                                "created_at": datetime.now().isoformat()
                            }
                        )
                    else:
                        error_text = await response.text()
                        return AdapterResult(
                            success=False,
                            error=f"OMS API返回错误: {response.status} - {error_text}"
                        )
        
        return AdapterResult(
            success=True,
            data={
                "order_id": params["order_no"],
                "order_no": params["order_no"],
                "status": "CREATED",
                "created_at": datetime.now().isoformat(),
                "_mock": True
            }
        )
    
    async def _get_order(
        self,
        params: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> AdapterResult:
        """获取订单信息"""
        order_no = params.get("order_no") or params.get("order_id")
        if not order_no:
            return AdapterResult(
                success=False,
                error="缺少订单号参数"
            )
        
        if self.base_url:
            url = self._build_url(f"/api/orders/{order_no}")
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    headers=self._get_headers(),
                    timeout=self.timeout
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return AdapterResult(success=True, data=data)
                    else:
                        return AdapterResult(
                            success=False,
                            error=f"订单不存在或查询失败: {order_no}"
                        )
        
        return AdapterResult(
            success=True,
            data={
                "order_id": order_no,
                "order_no": order_no,
                "status": params.get("status", "CREATED"),
                "customer_id": params.get("customer_id", ""),
                "items": params.get("items", []),
                "total_amount": params.get("total_amount", 0),
                "created_at": datetime.now().isoformat(),
                "_mock": True
            }
        )
    
    async def _update_order_status(
        self,
        params: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> AdapterResult:
        """更新订单状态"""
        order_no = params.get("order_no") or params.get("order_id")
        status = params.get("status")
        reason = params.get("reason", "")
        
        if not order_no or not status:
            return AdapterResult(
                success=False,
                error="缺少订单号或状态参数"
            )
        
        valid_statuses = [
            "CREATED", "PAID", "CONFIRMED", "ALLOCATED",
            "SHIPPING", "SHIPPED", "DELIVERED", "CANCELLED", "REFUNDED"
        ]
        
        if status not in valid_statuses:
            return AdapterResult(
                success=False,
                error=f"无效的订单状态: {status}, 有效值: {valid_statuses}"
            )
        
        if self.base_url:
            url = self._build_url(f"/api/orders/{order_no}/status")
            async with aiohttp.ClientSession() as session:
                async with session.put(
                    url,
                    json={"status": status, "reason": reason},
                    headers=self._get_headers(),
                    timeout=self.timeout
                ) as response:
                    if response.status == 200:
                        return AdapterResult(
                            success=True,
                            data={
                                "order_no": order_no,
                                "old_status": params.get("old_status", ""),
                                "new_status": status,
                                "updated_at": datetime.now().isoformat()
                            }
                        )
                    else:
                        error_text = await response.text()
                        return AdapterResult(
                            success=False,
                            error=f"更新订单状态失败: {error_text}"
                        )
        
        return AdapterResult(
            success=True,
            data={
                "order_no": order_no,
                "old_status": params.get("old_status", ""),
                "new_status": status,
                "updated_at": datetime.now().isoformat(),
                "_mock": True
            }
        )
    
    async def _cancel_order(
        self,
        params: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> AdapterResult:
        """取消订单"""
        params["status"] = "CANCELLED"
        return await self._update_order_status(params, context)
    
    async def _allocate_inventory(
        self,
        params: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> AdapterResult:
        """分配库存"""
        order_no = params.get("order_no")
        items = params.get("items", [])
        
        if not order_no:
            return AdapterResult(
                success=False,
                error="缺少订单号参数"
            )
        
        allocation_results = []
        for item in items:
            allocation_results.append({
                "sku": item.get("sku"),
                "quantity": item.get("quantity"),
                "allocated": True,
                "warehouse_id": item.get("warehouse_id", "WH001")
            })
        
        return AdapterResult(
            success=True,
            data={
                "order_no": order_no,
                "allocation_results": allocation_results,
                "allocated_at": datetime.now().isoformat()
            }
        )
    
    async def _search_orders(
        self,
        params: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> AdapterResult:
        """搜索订单"""
        criteria = params.get("criteria", {})
        page = params.get("page", 1)
        page_size = params.get("page_size", 20)
        
        return AdapterResult(
            success=True,
            data={
                "orders": [],
                "total": 0,
                "page": page,
                "page_size": page_size,
                "criteria": criteria
            }
        )
    
    async def _get_order_items(
        self,
        params: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> AdapterResult:
        """获取订单商品明细"""
        order_no = params.get("order_no")
        if not order_no:
            return AdapterResult(
                success=False,
                error="缺少订单号参数"
            )
        
        return AdapterResult(
            success=True,
            data={
                "order_no": order_no,
                "items": params.get("items", [])
            }
        )
    
    async def _update_order_address(
        self,
        params: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> AdapterResult:
        """更新订单收货地址"""
        order_no = params.get("order_no")
        address = params.get("address", {})
        
        if not order_no or not address:
            return AdapterResult(
                success=False,
                error="缺少订单号或地址参数"
            )
        
        return AdapterResult(
            success=True,
            data={
                "order_no": order_no,
                "address": address,
                "updated_at": datetime.now().isoformat()
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
            logger.warning(f"OMS健康检查失败: {e}")
            return False
