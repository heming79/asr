"""
企业级流程编排AI智能体
电商订单跨系统(OMS/WMS/TMS)自动化协同平台

使用示例:
    python main.py --help
    python main.py start
    python main.py configure-llm
"""

import asyncio
import argparse
import logging
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))

from ai_agent.config.config_manager import ConfigManager
from ai_agent.llm.llm_client import LLMClient
from ai_agent.orchestrator.models import (
    ProcessModel,
    Node,
    Edge,
    NodeType
)
from ai_agent.orchestrator.orchestrator import ProcessOrchestrator
from ai_agent.event_bus import EventBus
from ai_agent.monitoring import MonitoringSystem
from ai_agent.diagnostics import DiagnosticEngine
from ai_agent.testing import TestEngine
from ai_agent.adapters.oms_adapter import OMSAdapter
from ai_agent.adapters.wms_adapter import WMSAdapter
from ai_agent.adapters.tms_adapter import TMSAdapter

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def create_sample_order_process() -> ProcessModel:
    """创建示例订单处理流程模型"""
    nodes = [
        Node(
            id="start",
            name="开始",
            type=NodeType.START,
            description="流程开始节点"
        ),
        Node(
            id="create_order",
            name="创建订单",
            type=NodeType.TASK,
            config={
                "task_type": "oms",
                "adapter": "oms",
                "action": "create_order"
            },
            description="在OMS系统中创建订单"
        ),
        Node(
            id="validate_order",
            name="验证订单",
            type=NodeType.TASK,
            config={
                "task_type": "validation",
                "adapter": "oms",
                "action": "get_order"
            },
            description="验证订单信息完整性"
        ),
        Node(
            id="check_inventory",
            name="检查库存",
            type=NodeType.CONDITION,
            config={
                "conditions": [
                    {
                        "expression": "inventory_available == True",
                        "target": "allocate_inventory"
                    },
                    {
                        "expression": "inventory_available == False",
                        "target": "notify_out_of_stock"
                    }
                ],
                "default_target": "notify_out_of_stock"
            },
            description="检查库存是否充足"
        ),
        Node(
            id="allocate_inventory",
            name="分配库存",
            type=NodeType.TASK,
            config={
                "task_type": "wms",
                "adapter": "wms",
                "action": "allocate_inventory"
            },
            description="在WMS系统中分配库存"
        ),
        Node(
            id="create_shipment",
            name="创建运单",
            type=NodeType.TASK,
            config={
                "task_type": "tms",
                "adapter": "tms",
                "action": "create_shipment"
            },
            description="在TMS系统中创建运单"
        ),
        Node(
            id="assign_carrier",
            name="分配承运商",
            type=NodeType.TASK,
            config={
                "task_type": "tms",
                "adapter": "tms",
                "action": "assign_carrier"
            },
            description="分配物流承运商"
        ),
        Node(
            id="update_order_status",
            name="更新订单状态",
            type=NodeType.TASK,
            config={
                "task_type": "oms",
                "adapter": "oms",
                "action": "update_order_status"
            },
            description="更新订单状态为已发货"
        ),
        Node(
            id="notify_out_of_stock",
            name="通知缺货",
            type=NodeType.TASK,
            config={
                "task_type": "notification",
                "message": "商品缺货，请联系客户"
            },
            description="通知客户或运营人员缺货"
        ),
        Node(
            id="end_success",
            name="成功结束",
            type=NodeType.END,
            description="流程成功结束"
        ),
        Node(
            id="end_failed",
            name="失败结束",
            type=NodeType.END,
            description="流程失败结束"
        )
    ]
    
    edges = [
        Edge(id="e1", source="start", target="create_order"),
        Edge(id="e2", source="create_order", target="validate_order"),
        Edge(id="e3", source="validate_order", target="check_inventory"),
        Edge(id="e4", source="check_inventory", target="allocate_inventory", 
             condition="inventory_available == True", label="库存充足"),
        Edge(id="e5", source="check_inventory", target="notify_out_of_stock",
             condition="inventory_available == False", label="库存不足"),
        Edge(id="e6", source="allocate_inventory", target="create_shipment"),
        Edge(id="e7", source="create_shipment", target="assign_carrier"),
        Edge(id="e8", source="assign_carrier", target="update_order_status"),
        Edge(id="e9", source="update_order_status", target="end_success"),
        Edge(id="e10", source="notify_out_of_stock", target="end_failed")
    ]
    
    return ProcessModel(
        id="order_process_v1",
        name="电商订单处理流程",
        version="1.0.0",
        description="完整的电商订单跨系统处理流程，包含OMS订单创建、WMS库存分配、TMS物流配送",
        nodes=nodes,
        edges=edges,
        variables={
            "order_no": "",
            "customer_id": "",
            "items": [],
            "inventory_available": True,
            "shipping_address": {}
        }
    )


async def run_demo():
    """运行演示"""
    print("\n" + "="*70)
    print("  企业级流程编排AI智能体 - 演示模式")
    print("="*70)
    
    config_manager = ConfigManager()
    
    print("\n[1/6] 检查大模型配置...")
    if config_manager.check_llm_configured():
        print("    ✓ 检测到已保存的大模型配置")
        llm_config = config_manager.get_llm_config()
        print(f"    提供商: {llm_config.provider}")
        print(f"    模型: {llm_config.model}")
        llm_client = LLMClient(llm_config)
    else:
        print("    ⚠ 未检测到大模型配置，部分AI功能将不可用")
        print("    提示: 运行 'python main.py configure-llm' 配置大模型")
        llm_client = None
    
    print("\n[2/6] 初始化核心组件...")
    event_bus = EventBus()
    event_bus.start(worker_count=2)
    
    monitoring = MonitoringSystem()
    monitoring.start()
    
    diagnostic_engine = DiagnosticEngine(
        llm_client=llm_client,
        auto_repair_enabled=True
    )
    
    test_engine = TestEngine(llm_client=llm_client)
    
    print("    ✓ 事件总线已启动")
    print("    ✓ 监控系统已启动")
    print("    ✓ 诊断引擎已初始化")
    print("    ✓ 测试引擎已初始化")
    
    print("\n[3/6] 配置系统适配器...")
    adapters = {
        "oms": OMSAdapter({"base_url": "", "api_key": ""}),
        "wms": WMSAdapter({"base_url": "", "api_key": ""}),
        "tms": TMSAdapter({"base_url": "", "api_key": ""})
    }
    print("    ✓ OMS适配器已配置 (模拟模式)")
    print("    ✓ WMS适配器已配置 (模拟模式)")
    print("    ✓ TMS适配器已配置 (模拟模式)")
    
    print("\n[4/6] 创建订单处理流程模型...")
    process_model = create_sample_order_process()
    
    validation_errors = process_model.validate()
    if validation_errors:
        print(f"    ⚠ 流程模型验证警告: {validation_errors}")
    else:
        print("    ✓ 流程模型验证通过")
    
    print(f"\n    流程模型信息:")
    print(f"      - ID: {process_model.id}")
    print(f"      - 名称: {process_model.name}")
    print(f"      - 节点数: {len(process_model.nodes)}")
    print(f"      - 边数: {len(process_model.edges)}")
    
    print("\n[5/6] 创建流程编排器...")
    orchestrator = ProcessOrchestrator(
        process_model=process_model,
        event_bus=event_bus,
        monitoring=monitoring,
        adapters=adapters
    )
    print("    ✓ 流程编排器已创建")
    
    print("\n[6/6] 启动流程实例...")
    order_variables = {
        "order_no": f"ORD{asyncio.get_event_loop().time():.0f}",
        "customer_id": "CUST001",
        "items": [
            {"sku": "PROD001", "name": "商品A", "quantity": 2, "price": 99.99},
            {"sku": "PROD002", "name": "商品B", "quantity": 1, "price": 199.99}
        ],
        "inventory_available": True,
        "shipping_address": {
            "name": "张三",
            "phone": "13800138000",
            "address": "北京市朝阳区xxx街道xxx号",
            "city": "北京",
            "postal_code": "100000"
        },
        "total_amount": 399.97
    }
    
    print(f"\n    订单信息:")
    print(f"      - 订单号: {order_variables['order_no']}")
    print(f"      - 客户ID: {order_variables['customer_id']}")
    print(f"      - 商品数量: {len(order_variables['items'])}")
    print(f"      - 订单金额: ¥{order_variables['total_amount']}")
    
    instance = await orchestrator.start_process(variables=order_variables)
    print(f"\n    ✓ 流程实例已启动: {instance.id}")
    
    print("\n" + "-"*70)
    print("  等待流程执行完成...")
    print("-"*70)
    
    try:
        await asyncio.wait_for(
            orchestrator.wait_for_completion(instance.id),
            timeout=30.0
        )
        
        final_instance = orchestrator.get_process_instance(instance.id)
        if final_instance:
            print(f"\n    流程执行结果:")
            print(f"      - 状态: {final_instance.status.value}")
            print(f"      - 开始时间: {final_instance.start_time}")
            print(f"      - 结束时间: {final_instance.end_time}")
            
            if final_instance.status.value == "completed":
                duration = (final_instance.end_time - final_instance.start_time).total_seconds()
                print(f"      - 执行耗时: {duration:.3f}秒")
                print(f"\n    ✓ 流程执行成功!")
            else:
                print(f"      - 错误: {final_instance.error}")
    
    except asyncio.TimeoutError:
        print("\n    ⚠ 流程执行超时")
    
    print("\n" + "="*70)
    print("  系统统计信息")
    print("="*70)
    
    metrics = monitoring.get_metrics_summary()
    print(f"\n    指标统计:")
    print(f"      - 计数器: {metrics.get('counters', {})}")
    
    health = monitoring.get_health_status()
    print(f"\n    健康状态: {health['status']}")
    print(f"      - 活跃告警数: {health['active_alerts_count']}")
    
    print("\n" + "="*70)
    print("  演示完成")
    print("="*70)
    print("\n  下一步操作:")
    print("    1. 配置大模型: python main.py configure-llm")
    print("    2. 启动API服务: python main.py start")
    print("    3. 查看API文档: http://localhost:8000/docs")
    print("\n")
    
    await event_bus.stop()
    await monitoring.stop()


async def start_api_server(host: str = "0.0.0.0", port: int = 8000):
    """启动API服务器"""
    import uvicorn
    
    print("\n" + "="*70)
    print("  企业级流程编排AI智能体 - API服务")
    print("="*70)
    print(f"\n  服务地址: http://{host}:{port}")
    print(f"  API文档: http://{host}:{port}/docs")
    print(f"  健康检查: http://{host}:{port}/health")
    print("\n" + "="*70 + "\n")
    
    config = uvicorn.Config(
        "ai_agent.api.api:create_app",
        host=host,
        port=port,
        factory=True,
        log_level="info"
    )
    server = uvicorn.Server(config)
    await server.serve()


def main():
    """主入口"""
    parser = argparse.ArgumentParser(
        description="企业级流程编排AI智能体 - 电商订单跨系统自动化协同平台",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python main.py demo              运行演示模式
  python main.py start             启动API服务
  python main.py start --port 8080 启动API服务(指定端口)
  python main.py configure-llm     配置大模型
        """
    )
    
    subparsers = parser.add_subparsers(dest="command", help="可用命令")
    
    demo_parser = subparsers.add_parser("demo", help="运行演示模式")
    
    start_parser = subparsers.add_parser("start", help="启动API服务")
    start_parser.add_argument("--host", default="0.0.0.0", help="绑定地址 (默认: 0.0.0.0)")
    start_parser.add_argument("--port", type=int, default=8000, help="端口 (默认: 8000)")
    
    configure_parser = subparsers.add_parser("configure-llm", help="配置大模型")
    configure_parser.add_argument("--force", action="store_true", help="强制重新配置")
    
    args = parser.parse_args()
    
    if args.command == "demo":
        asyncio.run(run_demo())
    elif args.command == "start":
        asyncio.run(start_api_server(host=args.host, port=args.port))
    elif args.command == "configure-llm":
        config_manager = ConfigManager()
        config_manager.get_llm_config(force_prompt=args.force)
        print("\n✓ 大模型配置已保存")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
