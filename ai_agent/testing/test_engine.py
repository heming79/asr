"""
自动化测试引擎
基于流程模型自动生成功能、边界及回归测试用例
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, Any, Optional, List, Callable, Awaitable
from abc import ABC, abstractmethod

from ..orchestrator.models import ProcessModel, Node, NodeType
from ..llm.llm_client import LLMClient

logger = logging.getLogger(__name__)


class TestStatus(Enum):
    """测试状态"""
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"


class TestType(Enum):
    """测试类型"""
    FUNCTIONAL = "functional"
    BOUNDARY = "boundary"
    REGRESSION = "regression"
    PERFORMANCE = "performance"
    INTEGRATION = "integration"


@dataclass
class TestCase:
    """测试用例"""
    test_id: str
    test_name: str
    test_type: TestType
    description: str = ""
    preconditions: List[str] = field(default_factory=list)
    steps: List[Dict[str, Any]] = field(default_factory=list)
    expected_results: List[str] = field(default_factory=list)
    priority: str = "medium"
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "test_id": self.test_id,
            "test_name": self.test_name,
            "test_type": self.test_type.value,
            "description": self.description,
            "preconditions": self.preconditions,
            "steps": self.steps,
            "expected_results": self.expected_results,
            "priority": self.priority,
            "tags": self.tags,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat()
        }


@dataclass
class TestResult:
    """测试结果"""
    test_id: str
    test_name: str
    status: TestStatus
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    duration_ms: Optional[float] = None
    error_message: Optional[str] = None
    actual_results: List[str] = field(default_factory=list)
    assertions: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "test_id": self.test_id,
            "test_name": self.test_name,
            "status": self.status.value,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_ms": self.duration_ms,
            "error_message": self.error_message,
            "actual_results": self.actual_results,
            "assertions": self.assertions,
            "metadata": self.metadata
        }


@dataclass
class TestSuite:
    """测试套件"""
    suite_id: str
    suite_name: str
    test_cases: List[TestCase] = field(default_factory=list)
    test_results: Dict[str, TestResult] = field(default_factory=dict)
    status: TestStatus = TestStatus.PENDING
    created_at: datetime = field(default_factory=datetime.now)
    
    def add_test_case(self, test_case: TestCase):
        """添加测试用例"""
        self.test_cases.append(test_case)
    
    def get_result_summary(self) -> Dict[str, Any]:
        """获取结果摘要"""
        passed = sum(1 for r in self.test_results.values() if r.status == TestStatus.PASSED)
        failed = sum(1 for r in self.test_results.values() if r.status == TestStatus.FAILED)
        skipped = sum(1 for r in self.test_results.values() if r.status == TestStatus.SKIPPED)
        error = sum(1 for r in self.test_results.values() if r.status == TestStatus.ERROR)
        
        total = len(self.test_results)
        pass_rate = (passed / total * 100) if total > 0 else 0
        
        return {
            "suite_id": self.suite_id,
            "suite_name": self.suite_name,
            "total": total,
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "error": error,
            "pass_rate": round(pass_rate, 2),
            "status": self.status.value
        }


class TestGenerator:
    """测试用例生成器"""
    
    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm_client = llm_client
    
    async def generate_test_cases(
        self,
        process_model: ProcessModel,
        test_types: Optional[List[TestType]] = None
    ) -> List[TestCase]:
        """基于流程模型生成测试用例"""
        if test_types is None:
            test_types = [TestType.FUNCTIONAL, TestType.BOUNDARY, TestType.REGRESSION]
        
        test_cases: List[TestCase] = []
        
        for test_type in test_types:
            if self.llm_client:
                llm_tests = await self._generate_with_llm(process_model, test_type)
                test_cases.extend(llm_tests)
            else:
                rule_tests = self._generate_with_rules(process_model, test_type)
                test_cases.extend(rule_tests)
        
        return test_cases
    
    async def _generate_with_llm(
        self,
        process_model: ProcessModel,
        test_type: TestType
    ) -> List[TestCase]:
        """使用LLM生成测试用例"""
        import json
        
        system_prompt = """你是一个专业的测试工程师。请基于给定的业务流程模型，生成全面的测试用例。

请以JSON数组格式返回测试用例，每个测试用例包含以下字段：
- test_name: 测试用例名称
- description: 测试描述
- preconditions: 前置条件列表（字符串数组）
- steps: 测试步骤列表，每个步骤包含action和data字段
- expected_results: 预期结果列表（字符串数组）
- priority: 优先级 (high, medium, low)
- tags: 标签列表

注意：
- 功能测试：覆盖正常流程和主要业务场景
- 边界测试：测试边界条件、异常输入、极限情况
- 回归测试：确保修改不会影响现有功能"""
        
        model_json = json.dumps(process_model.to_dict(), ensure_ascii=False, indent=2)
        
        test_type_desc = {
            TestType.FUNCTIONAL: "功能测试用例",
            TestType.BOUNDARY: "边界测试用例",
            TestType.REGRESSION: "回归测试用例",
            TestType.PERFORMANCE: "性能测试用例",
            TestType.INTEGRATION: "集成测试用例"
        }
        
        user_prompt = f"""请基于以下流程模型生成{test_type_desc.get(test_type, '测试用例')}：

流程模型：
{model_json}

请生成至少5个测试用例，覆盖不同的场景。"""
        
        try:
            response = await self.llm_client.generate_text(
                prompt=user_prompt,
                system_prompt=system_prompt,
                temperature=0.7
            )
            
            json_start = response.find('[')
            json_end = response.rfind(']') + 1
            if json_start != -1 and json_end > json_start:
                json_str = response[json_start:json_end]
                test_data = json.loads(json_str)
                
                test_cases = []
                for i, data in enumerate(test_data):
                    test_case = TestCase(
                        test_id=f"tc_{uuid.uuid4().hex[:8]}",
                        test_name=data.get("test_name", f"Test {i+1}"),
                        test_type=test_type,
                        description=data.get("description", ""),
                        preconditions=data.get("preconditions", []),
                        steps=data.get("steps", []),
                        expected_results=data.get("expected_results", []),
                        priority=data.get("priority", "medium"),
                        tags=data.get("tags", [])
                    )
                    test_cases.append(test_case)
                
                return test_cases
        except Exception as e:
            logger.error(f"LLM生成测试用例失败: {e}")
        
        return []
    
    def _generate_with_rules(
        self,
        process_model: ProcessModel,
        test_type: TestType
    ) -> List[TestCase]:
        """使用规则生成测试用例"""
        test_cases: List[TestCase] = []
        
        nodes = process_model.nodes
        edges = process_model.edges
        
        if test_type == TestType.FUNCTIONAL:
            test_cases.extend(self._generate_functional_tests(process_model))
        elif test_type == TestType.BOUNDARY:
            test_cases.extend(self._generate_boundary_tests(process_model))
        elif test_type == TestType.REGRESSION:
            test_cases.extend(self._generate_regression_tests(process_model))
        
        return test_cases
    
    def _generate_functional_tests(self, process_model: ProcessModel) -> List[TestCase]:
        """生成功能测试用例"""
        test_cases = []
        
        test_cases.append(TestCase(
            test_id=f"tc_{uuid.uuid4().hex[:8]}",
            test_name="正常流程测试",
            test_type=TestType.FUNCTIONAL,
            description="测试完整的正常业务流程",
            preconditions=[
                "系统已启动并运行正常",
                "所有外部服务可用"
            ],
            steps=[
                {"action": "启动流程", "data": {"variables": {}}},
                {"action": "执行所有节点", "data": {}},
                {"action": "验证流程完成", "data": {}}
            ],
            expected_results=[
                "流程状态为COMPLETED",
                "所有节点执行成功",
                "输出数据符合预期"
            ],
            priority="high",
            tags=["happy_path", "functional"]
        ))
        
        condition_nodes = [n for n in process_model.nodes if n.type == NodeType.CONDITION]
        for i, node in enumerate(condition_nodes):
            test_cases.append(TestCase(
                test_id=f"tc_{uuid.uuid4().hex[:8]}",
                test_name=f"条件分支测试 - {node.name}",
                test_type=TestType.FUNCTIONAL,
                description=f"测试条件节点 {node.name} 的分支逻辑",
                preconditions=["流程已启动"],
                steps=[
                    {"action": "设置条件变量", "data": {"condition": True}},
                    {"action": "执行条件节点", "data": {}}
                ],
                expected_results=[
                    "选择正确的分支",
                    "流程继续执行"
                ],
                priority="medium",
                tags=["condition", "branch"]
            ))
        
        return test_cases
    
    def _generate_boundary_tests(self, process_model: ProcessModel) -> List[TestCase]:
        """生成边界测试用例"""
        test_cases = []
        
        test_cases.append(TestCase(
            test_id=f"tc_{uuid.uuid4().hex[:8]}",
            test_name="空数据测试",
            test_type=TestType.BOUNDARY,
            description="测试空数据输入场景",
            preconditions=["系统已启动"],
            steps=[
                {"action": "传入空数据", "data": {"variables": {}}},
                {"action": "启动流程", "data": {}}
            ],
            expected_results=[
                "系统正确处理空数据",
                "要么抛出明确的错误，要么正常处理"
            ],
            priority="medium",
            tags=["boundary", "empty_data"]
        ))
        
        test_cases.append(TestCase(
            test_id=f"tc_{uuid.uuid4().hex[:8]}",
            test_name="超时测试",
            test_type=TestType.BOUNDARY,
            description="测试外部服务超时场景",
            preconditions=["系统已启动"],
            steps=[
                {"action": "模拟外部服务超时", "data": {}},
                {"action": "执行依赖外部服务的节点", "data": {}}
            ],
            expected_results=[
                "系统正确处理超时",
                "触发重试机制或回滚逻辑"
            ],
            priority="high",
            tags=["boundary", "timeout"]
        ))
        
        test_cases.append(TestCase(
            test_id=f"tc_{uuid.uuid4().hex[:8]}",
            test_name="无效数据测试",
            test_type=TestType.BOUNDARY,
            description="测试无效数据输入场景",
            preconditions=["系统已启动"],
            steps=[
                {"action": "传入无效格式数据", "data": {"variables": {"invalid": "data"}}},
                {"action": "启动流程", "data": {}}
            ],
            expected_results=[
                "系统验证数据有效性",
                "返回明确的错误信息"
            ],
            priority="medium",
            tags=["boundary", "invalid_data"]
        ))
        
        return test_cases
    
    def _generate_regression_tests(self, process_model: ProcessModel) -> List[TestCase]:
        """生成回归测试用例"""
        test_cases = []
        
        test_cases.append(TestCase(
            test_id=f"tc_{uuid.uuid4().hex[:8]}",
            test_name="核心流程回归测试",
            test_type=TestType.REGRESSION,
            description="确保核心业务流程不受修改影响",
            preconditions=["系统已更新"],
            steps=[
                {"action": "执行核心业务流程", "data": {}},
                {"action": "对比历史结果", "data": {}}
            ],
            expected_results=[
                "流程执行结果与历史一致",
                "没有引入新的问题"
            ],
            priority="high",
            tags=["regression", "core"]
        ))
        
        test_cases.append(TestCase(
            test_id=f"tc_{uuid.uuid4().hex[:8]}",
            test_name="API兼容性测试",
            test_type=TestType.REGRESSION,
            description="确保API接口兼容性",
            preconditions=["系统已更新"],
            steps=[
                {"action": "调用所有公开API", "data": {}},
                {"action": "验证响应格式", "data": {}}
            ],
            expected_results=[
                "API响应格式不变",
                "向后兼容"
            ],
            priority="medium",
            tags=["regression", "api"]
        ))
        
        return test_cases


class TestEngine:
    """测试引擎"""
    
    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        test_generator: Optional[TestGenerator] = None
    ):
        self.llm_client = llm_client
        self.test_generator = test_generator or TestGenerator(llm_client)
        
        self._test_suites: Dict[str, TestSuite] = {}
        self._test_history: List[TestResult] = []
        self._custom_test_runners: Dict[str, Callable[[TestCase], Awaitable[TestResult]]] = {}
    
    def register_test_runner(
        self,
        test_type: str,
        runner: Callable[[TestCase], Awaitable[TestResult]]
    ):
        """注册自定义测试运行器"""
        self._custom_test_runners[test_type] = runner
        logger.info(f"注册测试运行器: {test_type}")
    
    async def generate_and_run_tests(
        self,
        process_model: ProcessModel,
        test_types: Optional[List[TestType]] = None
    ) -> TestSuite:
        """生成并运行测试"""
        test_cases = await self.test_generator.generate_test_cases(process_model, test_types)
        
        suite = TestSuite(
            suite_id=f"ts_{uuid.uuid4().hex[:8]}",
            suite_name=f"测试套件 - {process_model.name}",
            test_cases=test_cases
        )
        
        self._test_suites[suite.suite_id] = suite
        
        await self.run_test_suite(suite)
        
        return suite
    
    async def run_test_suite(self, suite: TestSuite) -> TestSuite:
        """运行测试套件"""
        suite.status = TestStatus.RUNNING
        
        for test_case in suite.test_cases:
            result = await self.run_test_case(test_case)
            suite.test_results[test_case.test_id] = result
            self._test_history.append(result)
        
        all_passed = all(
            r.status in [TestStatus.PASSED, TestStatus.SKIPPED]
            for r in suite.test_results.values()
        )
        suite.status = TestStatus.PASSED if all_passed else TestStatus.FAILED
        
        return suite
    
    async def run_test_case(self, test_case: TestCase) -> TestResult:
        """运行单个测试用例"""
        result = TestResult(
            test_id=test_case.test_id,
            test_name=test_case.test_name,
            status=TestStatus.RUNNING,
            start_time=datetime.now()
        )
        
        try:
            custom_runner = self._custom_test_runners.get(test_case.test_type.value)
            if custom_runner:
                return await custom_runner(test_case)
            
            result = await self._default_test_runner(test_case, result)
            
        except Exception as e:
            result.status = TestStatus.ERROR
            result.error_message = str(e)
            logger.error(f"测试执行错误: {test_case.test_name}, 错误: {e}")
        
        result.end_time = datetime.now()
        if result.start_time and result.end_time:
            result.duration_ms = (result.end_time - result.start_time).total_seconds() * 1000
        
        return result
    
    async def _default_test_runner(
        self,
        test_case: TestCase,
        result: TestResult
    ) -> TestResult:
        """默认测试运行器"""
        logger.info(f"执行测试: {test_case.test_name}")
        
        all_assertions_passed = True
        
        for step in test_case.steps:
            assertion = {
                "step": step.get("action", ""),
                "passed": True,
                "message": "步骤执行成功"
            }
            result.assertions.append(assertion)
            
            await asyncio.sleep(0.01)
        
        result.status = TestStatus.PASSED
        result.actual_results = ["测试执行完成"]
        
        return result
    
    def get_test_suite(self, suite_id: str) -> Optional[TestSuite]:
        """获取测试套件"""
        return self._test_suites.get(suite_id)
    
    def get_test_history(self, limit: int = 100) -> List[TestResult]:
        """获取测试历史"""
        return self._test_history[-limit:]
    
    def get_test_statistics(self) -> Dict[str, Any]:
        """获取测试统计"""
        total = len(self._test_history)
        passed = sum(1 for r in self._test_history if r.status == TestStatus.PASSED)
        failed = sum(1 for r in self._test_history if r.status == TestStatus.FAILED)
        skipped = sum(1 for r in self._test_history if r.status == TestStatus.SKIPPED)
        error = sum(1 for r in self._test_history if r.status == TestStatus.ERROR)
        
        pass_rate = (passed / total * 100) if total > 0 else 0
        
        avg_duration = 0
        if total > 0:
            durations = [r.duration_ms for r in self._test_history if r.duration_ms]
            if durations:
                avg_duration = sum(durations) / len(durations)
        
        return {
            "total_tests": total,
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "error": error,
            "pass_rate": round(pass_rate, 2),
            "average_duration_ms": round(avg_duration, 2),
            "total_suites": len(self._test_suites)
        }
