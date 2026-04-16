"""
大模型客户端
支持多种大模型提供商：OpenAI、Azure、Anthropic、本地模型等
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, AsyncIterator
from abc import ABC, abstractmethod

import aiohttp

from ..config.config_manager import LLMConfig

logger = logging.getLogger(__name__)


@dataclass
class Message:
    """消息对象"""
    role: str
    content: str
    name: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        result = {"role": self.role, "content": self.content}
        if self.name:
            result["name"] = self.name
        return result


@dataclass
class LLMResponse:
    """大模型响应"""
    content: str
    model: str
    usage: Dict[str, int] = field(default_factory=dict)
    finish_reason: Optional[str] = None
    raw_response: Dict[str, Any] = field(default_factory=dict)


class BaseLLMProvider(ABC):
    """大模型提供商基类"""
    
    def __init__(self, config: LLMConfig):
        self.config = config
    
    @abstractmethod
    async def chat(
        self,
        messages: List[Message],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> LLMResponse:
        """发送聊天请求"""
        pass
    
    @abstractmethod
    async def chat_stream(
        self,
        messages: List[Message],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> AsyncIterator[str]:
        """流式聊天"""
        pass


class OpenAIProvider(BaseLLMProvider):
    """OpenAI 提供商"""
    
    def __init__(self, config: LLMConfig):
        super().__init__(config)
        self.api_base = config.api_base or "https://api.openai.com/v1"
        self.api_key = config.api_key
        self.model = config.model
    
    def _get_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
    
    async def chat(
        self,
        messages: List[Message],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> LLMResponse:
        url = f"{self.api_base}/chat/completions"
        
        payload = {
            "model": self.model,
            "messages": [m.to_dict() for m in messages],
            "temperature": temperature or self.config.temperature,
            "max_tokens": max_tokens or self.config.max_tokens,
            **kwargs
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=self._get_headers(), json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"OpenAI API error: {response.status} - {error_text}")
                
                data = await response.json()
                
                return LLMResponse(
                    content=data["choices"][0]["message"]["content"],
                    model=data.get("model", self.model),
                    usage=data.get("usage", {}),
                    finish_reason=data["choices"][0].get("finish_reason"),
                    raw_response=data
                )
    
    async def chat_stream(
        self,
        messages: List[Message],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> AsyncIterator[str]:
        url = f"{self.api_base}/chat/completions"
        
        payload = {
            "model": self.model,
            "messages": [m.to_dict() for m in messages],
            "temperature": temperature or self.config.temperature,
            "max_tokens": max_tokens or self.config.max_tokens,
            "stream": True,
            **kwargs
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=self._get_headers(), json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"OpenAI API error: {response.status} - {error_text}")
                
                async for line in response.content:
                    line = line.decode('utf-8').strip()
                    if line.startswith('data: '):
                        data_str = line[6:]
                        if data_str == '[DONE]':
                            break
                        try:
                            data = json.loads(data_str)
                            if data.get('choices') and data['choices'][0].get('delta', {}).get('content'):
                                yield data['choices'][0]['delta']['content']
                        except json.JSONDecodeError:
                            continue


class AnthropicProvider(BaseLLMProvider):
    """Anthropic (Claude) 提供商"""
    
    def __init__(self, config: LLMConfig):
        super().__init__(config)
        self.api_base = config.api_base or "https://api.anthropic.com/v1"
        self.api_key = config.api_key
        self.model = config.model
    
    def _get_headers(self) -> Dict[str, str]:
        return {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json"
        }
    
    def _convert_messages(self, messages: List[Message]) -> List[Dict[str, Any]]:
        converted = []
        for msg in messages:
            if msg.role == "system":
                continue
            converted.append({"role": msg.role, "content": msg.content})
        return converted
    
    def _get_system_prompt(self, messages: List[Message]) -> Optional[str]:
        for msg in messages:
            if msg.role == "system":
                return msg.content
        return None
    
    async def chat(
        self,
        messages: List[Message],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> LLMResponse:
        url = f"{self.api_base}/messages"
        
        system_prompt = self._get_system_prompt(messages)
        converted_messages = self._convert_messages(messages)
        
        payload = {
            "model": self.model,
            "messages": converted_messages,
            "max_tokens": max_tokens or self.config.max_tokens,
            "temperature": temperature or self.config.temperature,
            **kwargs
        }
        
        if system_prompt:
            payload["system"] = system_prompt
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=self._get_headers(), json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Anthropic API error: {response.status} - {error_text}")
                
                data = await response.json()
                
                content = ""
                if data.get('content'):
                    for block in data['content']:
                        if block.get('type') == 'text':
                            content += block.get('text', '')
                
                return LLMResponse(
                    content=content,
                    model=data.get("model", self.model),
                    usage=data.get("usage", {}),
                    finish_reason=data.get("stop_reason"),
                    raw_response=data
                )
    
    async def chat_stream(
        self,
        messages: List[Message],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> AsyncIterator[str]:
        url = f"{self.api_base}/messages"
        
        system_prompt = self._get_system_prompt(messages)
        converted_messages = self._convert_messages(messages)
        
        payload = {
            "model": self.model,
            "messages": converted_messages,
            "max_tokens": max_tokens or self.config.max_tokens,
            "temperature": temperature or self.config.temperature,
            "stream": True,
            **kwargs
        }
        
        if system_prompt:
            payload["system"] = system_prompt
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=self._get_headers(), json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Anthropic API error: {response.status} - {error_text}")
                
                async for line in response.content:
                    line = line.decode('utf-8').strip()
                    if line.startswith('data: '):
                        data_str = line[6:]
                        try:
                            data = json.loads(data_str)
                            if data.get('type') == 'content_block_delta':
                                delta = data.get('delta', {})
                                if delta.get('text'):
                                    yield delta['text']
                        except json.JSONDecodeError:
                            continue


class LLMClient:
    """大模型客户端统一接口"""
    
    _providers: Dict[str, type] = {
        "openai": OpenAIProvider,
        "azure": OpenAIProvider,
        "anthropic": AnthropicProvider,
        "local": OpenAIProvider,
        "custom": OpenAIProvider
    }
    
    def __init__(self, config: LLMConfig):
        self.config = config
        self._provider = self._create_provider(config)
    
    def _create_provider(self, config: LLMConfig) -> BaseLLMProvider:
        provider_class = self._providers.get(config.provider, OpenAIProvider)
        return provider_class(config)
    
    async def chat(
        self,
        messages: List[Message],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> LLMResponse:
        """
        发送聊天请求
        
        Args:
            messages: 消息列表
            temperature: 温度参数
            max_tokens: 最大token数
            **kwargs: 其他参数
        
        Returns:
            LLMResponse: 响应对象
        """
        logger.debug(f"Sending chat request to {self.config.provider} with {len(messages)} messages")
        try:
            response = await self._provider.chat(messages, temperature, max_tokens, **kwargs)
            logger.debug(f"Received response from {self.config.provider}")
            return response
        except Exception as e:
            logger.error(f"Chat request failed: {e}")
            raise
    
    async def chat_stream(
        self,
        messages: List[Message],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> AsyncIterator[str]:
        """
        流式聊天
        
        Args:
            messages: 消息列表
            temperature: 温度参数
            max_tokens: 最大token数
            **kwargs: 其他参数
        
        Yields:
            str: 流式输出的文本片段
        """
        logger.debug(f"Starting stream chat with {self.config.provider}")
        async for chunk in self._provider.chat_stream(messages, temperature, max_tokens, **kwargs):
            yield chunk
    
    async def generate_text(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> str:
        """
        生成文本的便捷方法
        
        Args:
            prompt: 用户提示
            system_prompt: 系统提示
            temperature: 温度参数
            max_tokens: 最大token数
            **kwargs: 其他参数
        
        Returns:
            str: 生成的文本
        """
        messages = []
        if system_prompt:
            messages.append(Message(role="system", content=system_prompt))
        messages.append(Message(role="user", content=prompt))
        
        response = await self.chat(messages, temperature, max_tokens, **kwargs)
        return response.content
    
    async def analyze_logs(
        self,
        logs: List[str],
        context: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        分析日志，用于智能诊断
        
        Args:
            logs: 日志列表
            context: 上下文信息
        
        Returns:
            Dict: 分析结果
        """
        system_prompt = """你是一个专业的系统运维和日志分析专家。请分析以下日志，找出可能的问题根因，并提供修复建议。

请以JSON格式返回分析结果，包含以下字段：
- root_cause: 问题根因描述
- severity: 严重程度 (critical, high, medium, low)
- affected_systems: 受影响的系统列表
- suggested_fixes: 建议的修复措施列表
- confidence: 分析置信度 (0-100)
"""
        
        log_content = "\n".join(logs[-100:]) if len(logs) > 100 else "\n".join(logs)
        
        user_prompt = f"请分析以下日志：\n\n{log_content}"
        if context:
            user_prompt += f"\n\n上下文信息：{context}"
        
        response = await self.generate_text(
            prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=0.3
        )
        
        try:
            json_start = response.find('{')
            json_end = response.rfind('}') + 1
            if json_start != -1 and json_end > json_start:
                json_str = response[json_start:json_end]
                return json.loads(json_str)
        except json.JSONDecodeError:
            pass
        
        return {
            "root_cause": response,
            "severity": "unknown",
            "affected_systems": [],
            "suggested_fixes": [],
            "confidence": 0
        }
    
    async def generate_test_cases(
        self,
        process_model: Dict[str, Any],
        test_type: str = "all"
    ) -> List[Dict[str, Any]]:
        """
        基于流程模型生成测试用例
        
        Args:
            process_model: 流程模型
            test_type: 测试类型 (all, functional, boundary, regression)
        
        Returns:
            List[Dict]: 测试用例列表
        """
        system_prompt = """你是一个专业的测试工程师。请基于给定的业务流程模型，生成全面的测试用例。

请以JSON数组格式返回测试用例，每个测试用例包含以下字段：
- test_id: 测试用例ID
- test_name: 测试用例名称
- test_type: 测试类型 (functional, boundary, regression, performance)
- description: 测试描述
- preconditions: 前置条件列表
- steps: 测试步骤列表
- expected_results: 预期结果列表
- priority: 优先级 (high, medium, low)
"""
        
        model_json = json.dumps(process_model, ensure_ascii=False, indent=2)
        
        test_type_desc = {
            "all": "所有类型的测试用例",
            "functional": "功能测试用例",
            "boundary": "边界测试用例",
            "regression": "回归测试用例"
        }
        
        user_prompt = f"""请基于以下流程模型生成{test_type_desc.get(test_type, '测试用例')}：

流程模型：
{model_json}

请生成全面的测试用例，覆盖正常流程、异常流程、边界条件等场景。"""
        
        response = await self.generate_text(
            prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=0.7
        )
        
        try:
            json_start = response.find('[')
            json_end = response.rfind(']') + 1
            if json_start != -1 and json_end > json_start:
                json_str = response[json_start:json_end]
                return json.loads(json_str)
        except json.JSONDecodeError:
            pass
        
        return []
