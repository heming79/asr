"""
WMS (仓储管理系统) 适配器
负责与仓储管理系统进行交互
"""

import logging
import aiohttp
from typing import Dict, Any, Optional, List
from datetime import datetime

from .base import BaseAdapter, AdapterResult

logger = logging.getLogger(__name__)


class WMSAdapter(BaseAdapter):
    """WMS适配器"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.system_name = "WMS"
    
    async def execute(
        self,
        action: str,
        params: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> AdapterResult:
        """执行WMS操作"""
        logger.info(f"执行WMS操作: {action}, 参数: {params}")
        
        action_handlers = {
            "create_warehouse_order": self._create_warehouse_order,
            "get_inventory": self._get_inventory,
            "allocate_inventory": self._allocate_inventory,
            "lock_inventory": self._lock_inventory,
            "unlock_inventory": self._unlock_inventory,
            "create_picking_task": self._create_picking_task,
            "confirm_picking": self._confirm_picking,
            "create_packing_task": self._create_packing_task,
            "confirm_packing": self._confirm_packing,
            "get_warehouse_order": self._get_warehouse_order,
            "update_warehouse_order_status": self._update_warehouse_order_status,
        }
        
        handler = action_handlers.get(action)
        if not handler:
            return AdapterResult(
                success=False,
                error=f"未知的WMS操作: {action}"
            )
        
        try:
            return await handler(params, context)
        except Exception as e:
            logger.error(f"WMS操作执行失败: {action}, 错误: {e}")
            return AdapterResult(
                success=False,
                error=str(e),
                metadata={"action": action}
            )
    
    async def _create_warehouse_order(
        self,
        params: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> AdapterResult:
        """创建仓储订单"""
        order_no = params.get("order_no")
        items = params.get("items", [])
        warehouse_id = params.get("warehouse_id", "WH001")
        
        if not order_no or not items:
            return AdapterResult(
                success=False,
                error="缺少订单号或商品明细"
            )
        
        warehouse_order_no = f"WO{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        if self.base_url:
            url = self._build_url("/api/warehouse-orders")
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json={
                        "order_no": order_no,
                        "warehouse_order_no": warehouse_order_no,
                        "warehouse_id": warehouse_id,
                        "items": items,
                        "type": params.get("type", "OUTBOUND")
                    },
                    headers=self._get_headers(),
                    timeout=self.timeout
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        return AdapterResult(
                            success=True,
                            data={
                                "warehouse_order_no": result.get("warehouse_order_no", warehouse_order_no),
                                "order_no": order_no,
                                "warehouse_id": warehouse_id,
                                "status": "CREATED",
                                "created_at": datetime.now().isoformat()
                            }
                        )
        
        return AdapterResult(
            success=True,
            data={
                "warehouse_order_no": warehouse_order_no,
                "order_no": order_no,
                "warehouse_id": warehouse_id,
                "status": "CREATED",
                "created_at": datetime.now().isoformat(),
                "_mock": True
            }
        )
    
    async def _get_inventory(
        self,
        params: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> AdapterResult:
        """查询库存"""
        sku = params.get("sku")
        warehouse_id = params.get("warehouse_id")
        
        if self.base_url:
            url = self._build_url("/api/inventory")
            query_params = {}
            if sku:
                query_params["sku"] = sku
            if warehouse_id:
                query_params["warehouse_id"] = warehouse_id
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    params=query_params,
                    headers=self._get_headers(),
                    timeout=self.timeout
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return AdapterResult(success=True, data=data)
        
        return AdapterResult(
            success=True,
            data={
                "sku": sku,
                "warehouse_id": warehouse_id,
                "available_quantity": params.get("available_quantity", 100),
                "locked_quantity": params.get("locked_quantity", 0),
                "_mock": True
            }
        )
    
    async def _allocate_inventory(
        self,
        params: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> AdapterResult:
        """分配库存"""
        order_no = params.get("order_no")
        items = params.get("items", [])
        warehouse_id = params.get("warehouse_id", "WH001")
        
        if not order_no or not items:
            return AdapterResult(
                success=False,
                error="缺少订单号或商品明细"
            )
        
        allocation_results = []
        for item in items:
            sku = item.get("sku")
            quantity = item.get("quantity", 0)
            allocation_results.append({
                "sku": sku,
                "quantity": quantity,
                "allocated": True,
                "warehouse_id": warehouse_id,
                "location": item.get("location", "A-01-01")
            })
        
        return AdapterResult(
            success=True,
            data={
                "order_no": order_no,
                "warehouse_id": warehouse_id,
                "allocation_results": allocation_results,
                "allocated_at": datetime.now().isoformat()
            }
        )
    
    async def _lock_inventory(
        self,
        params: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> AdapterResult:
        """锁定库存"""
        sku = params.get("sku")
        quantity = params.get("quantity", 0)
        warehouse_id = params.get("warehouse_id", "WH001")
        lock_reason = params.get("lock_reason", "ORDER_LOCK")
        
        if not sku or quantity <= 0:
            return AdapterResult(
                success=False,
                error="缺少SKU或数量无效"
            )
        
        return AdapterResult(
            success=True,
            data={
                "sku": sku,
                "quantity": quantity,
                "warehouse_id": warehouse_id,
                "lock_reason": lock_reason,
                "locked_at": datetime.now().isoformat()
            }
        )
    
    async def _unlock_inventory(
        self,
        params: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> AdapterResult:
        """解锁库存"""
        sku = params.get("sku")
        quantity = params.get("quantity", 0)
        warehouse_id = params.get("warehouse_id", "WH001")
        
        if not sku or quantity <= 0:
            return AdapterResult(
                success=False,
                error="缺少SKU或数量无效"
            )
        
        return AdapterResult(
            success=True,
            data={
                "sku": sku,
                "quantity": quantity,
                "warehouse_id": warehouse_id,
                "unlocked_at": datetime.now().isoformat()
            }
        )
    
    async def _create_picking_task(
        self,
        params: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> AdapterResult:
        """创建拣货任务"""
        warehouse_order_no = params.get("warehouse_order_no")
        items = params.get("items", [])
        
        if not warehouse_order_no:
            return AdapterResult(
                success=False,
                error="缺少仓储订单号"
            )
        
        picking_task_no = f"PT{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        return AdapterResult(
            success=True,
            data={
                "picking_task_no": picking_task_no,
                "warehouse_order_no": warehouse_order_no,
                "items": items,
                "status": "PENDING",
                "created_at": datetime.now().isoformat()
            }
        )
    
    async def _confirm_picking(
        self,
        params: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> AdapterResult:
        """确认拣货完成"""
        picking_task_no = params.get("picking_task_no")
        operator = params.get("operator", "system")
        
        if not picking_task_no:
            return AdapterResult(
                success=False,
                error="缺少拣货任务号"
            )
        
        return AdapterResult(
            success=True,
            data={
                "picking_task_no": picking_task_no,
                "operator": operator,
                "confirmed_at": datetime.now().isoformat()
            }
        )
    
    async def _create_packing_task(
        self,
        params: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> AdapterResult:
        """创建打包任务"""
        warehouse_order_no = params.get("warehouse_order_no")
        items = params.get("items", [])
        
        if not warehouse_order_no:
            return AdapterResult(
                success=False,
                error="缺少仓储订单号"
            )
        
        packing_task_no = f"PK{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        return AdapterResult(
            success=True,
            data={
                "packing_task_no": packing_task_no,
                "warehouse_order_no": warehouse_order_no,
                "items": items,
                "status": "PENDING",
                "created_at": datetime.now().isoformat()
            }
        )
    
    async def _confirm_packing(
        self,
        params: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> AdapterResult:
        """确认打包完成"""
        packing_task_no = params.get("packing_task_no")
        package_info = params.get("package_info", {})
        operator = params.get("operator", "system")
        
        if not packing_task_no:
            return AdapterResult(
                success=False,
                error="缺少打包任务号"
            )
        
        return AdapterResult(
            success=True,
            data={
                "packing_task_no": packing_task_no,
                "package_info": package_info,
                "operator": operator,
                "confirmed_at": datetime.now().isoformat()
            }
        )
    
    async def _get_warehouse_order(
        self,
        params: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> AdapterResult:
        """获取仓储订单"""
        warehouse_order_no = params.get("warehouse_order_no")
        
        if not warehouse_order_no:
            return AdapterResult(
                success=False,
                error="缺少仓储订单号"
            )
        
        return AdapterResult(
            success=True,
            data={
                "warehouse_order_no": warehouse_order_no,
                "order_no": params.get("order_no", ""),
                "status": params.get("status", "CREATED"),
                "items": params.get("items", []),
                "_mock": True
            }
        )
    
    async def _update_warehouse_order_status(
        self,
        params: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> AdapterResult:
        """更新仓储订单状态"""
        warehouse_order_no = params.get("warehouse_order_no")
        status = params.get("status")
        
        if not warehouse_order_no or not status:
            return AdapterResult(
                success=False,
                error="缺少仓储订单号或状态"
            )
        
        valid_statuses = [
            "CREATED", "ALLOCATED", "PICKING", "PICKED",
            "PACKING", "PACKED", "SHIPPING", "SHIPPED", "CANCELLED"
        ]
        
        if status not in valid_statuses:
            return AdapterResult(
                success=False,
                error=f"无效的仓储订单状态: {status}"
            )
        
        return AdapterResult(
            success=True,
            data={
                "warehouse_order_no": warehouse_order_no,
                "status": status,
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
            logger.warning(f"WMS健康检查失败: {e}")
            return False
