"""
配置管理器
负责管理大模型配置、系统配置等
"""

import os
import json
import getpass
from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any
from pathlib import Path


@dataclass
class LLMConfig:
    """大模型配置"""
    provider: str = "openai"
    api_key: str = ""
    api_base: str = ""
    model: str = "gpt-4"
    temperature: float = 0.7
    max_tokens: int = 4096
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'LLMConfig':
        return cls(**data)


@dataclass
class SystemConfig:
    """系统配置"""
    oms_api_url: str = "http://localhost:8081/api"
    wms_api_url: str = "http://localhost:8082/api"
    tms_api_url: str = "http://localhost:8083/api"
    event_bus_url: str = "redis://localhost:6379/0"
    monitoring_enabled: bool = True
    diagnostics_enabled: bool = True
    auto_recovery_enabled: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SystemConfig':
        return cls(**data)


class ConfigManager:
    """配置管理器"""
    
    DEFAULT_CONFIG_DIR = Path.home() / ".ai_agent"
    LLM_CONFIG_FILE = "llm_config.json"
    SYSTEM_CONFIG_FILE = "system_config.json"
    
    def __init__(self, config_dir: Optional[str] = None):
        self.config_dir = Path(config_dir) if config_dir else self.DEFAULT_CONFIG_DIR
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
        self._llm_config: Optional[LLMConfig] = None
        self._system_config: Optional[SystemConfig] = None
    
    def prompt_for_llm_config(self) -> LLMConfig:
        """提示用户输入大模型配置"""
        print("\n" + "="*60)
        print("请配置大模型连接信息（配置将保存到本地，避免重复输入）")
        print("="*60)
        
        print("\n支持的大模型提供商:")
        print("  1. OpenAI (GPT-4, GPT-3.5)")
        print("  2. Azure OpenAI")
        print("  3. Anthropic (Claude)")
        print("  4. 本地部署模型 (如 Ollama)")
        print("  5. 其他兼容OpenAI API的模型")
        
        provider_map = {
            "1": "openai",
            "2": "azure",
            "3": "anthropic",
            "4": "local",
            "5": "custom"
        }
        
        while True:
            choice = input("\n请选择提供商 (1-5): ").strip()
            if choice in provider_map:
                provider = provider_map[choice]
                break
            print("无效选择，请重新输入")
        
        api_key = getpass.getpass("请输入 API Key: ").strip()
        
        if provider == "azure":
            api_base = input("请输入 Azure API Base URL: ").strip()
            model = input("请输入模型部署名称 (默认: gpt-4): ").strip() or "gpt-4"
        elif provider == "anthropic":
            api_base = "https://api.anthropic.com"
            model = input("请输入模型名称 (默认: claude-3-opus-20240229): ").strip() or "claude-3-opus-20240229"
        elif provider == "local":
            api_base = input("请输入本地模型API地址 (默认: http://localhost:11434/v1): ").strip() or "http://localhost:11434/v1"
            model = input("请输入模型名称 (默认: llama3): ").strip() or "llama3"
        else:
            api_base = input("请输入 API Base URL (可选，留空使用默认): ").strip()
            model = input("请输入模型名称 (默认: gpt-4): ").strip() or "gpt-4"
        
        config = LLMConfig(
            provider=provider,
            api_key=api_key,
            api_base=api_base,
            model=model
        )
        
        save = input("\n是否保存配置以便下次使用? (y/n): ").strip().lower()
        if save == 'y':
            self.save_llm_config(config)
            print(f"配置已保存到: {self.config_dir / self.LLM_CONFIG_FILE}")
        
        self._llm_config = config
        return config
    
    def save_llm_config(self, config: LLMConfig) -> None:
        """保存大模型配置到文件"""
        config_path = self.config_dir / self.LLM_CONFIG_FILE
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config.to_dict(), f, indent=2, ensure_ascii=False)
    
    def load_llm_config(self) -> Optional[LLMConfig]:
        """从文件加载大模型配置"""
        config_path = self.config_dir / self.LLM_CONFIG_FILE
        if config_path.exists():
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self._llm_config = LLMConfig.from_dict(data)
                return self._llm_config
            except Exception as e:
                print(f"加载配置文件失败: {e}")
        return None
    
    def get_llm_config(self, force_prompt: bool = False) -> LLMConfig:
        """获取大模型配置，如果不存在则提示用户输入"""
        if force_prompt or self._llm_config is None:
            existing = self.load_llm_config()
            if existing and not force_prompt:
                return existing
            return self.prompt_for_llm_config()
        return self._llm_config
    
    def save_system_config(self, config: SystemConfig) -> None:
        """保存系统配置"""
        config_path = self.config_dir / self.SYSTEM_CONFIG_FILE
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config.to_dict(), f, indent=2, ensure_ascii=False)
    
    def load_system_config(self) -> SystemConfig:
        """加载系统配置"""
        config_path = self.config_dir / self.SYSTEM_CONFIG_FILE
        if config_path.exists():
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self._system_config = SystemConfig.from_dict(data)
                return self._system_config
            except Exception as e:
                print(f"加载系统配置失败: {e}")
        
        self._system_config = SystemConfig()
        return self._system_config
    
    def get_system_config(self) -> SystemConfig:
        """获取系统配置"""
        if self._system_config is None:
            return self.load_system_config()
        return self._system_config
    
    def check_llm_configured(self) -> bool:
        """检查大模型是否已配置"""
        if self._llm_config and self._llm_config.api_key:
            return True
        existing = self.load_llm_config()
        return existing is not None and existing.api_key != ""
