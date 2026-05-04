"""
Unified LLM Runtime

统一 LLM 调用运行时，取代分散在各处的 openai.AsyncOpenAI。
支持按任务类型配置不同模型，但走统一的 client / retry / timeout / logging / fallback。

任务类型：
- chat: 主对话生成（用最好的模型）
- intent: 意图分析（轻量、快）
- review: 回复评审（轻量）
- tool: 工具推理（中等）
- planning: 规划/排序（中等）
"""

from __future__ import annotations

# 加载 .env 文件中的环境变量
from dotenv import load_dotenv
load_dotenv()

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Callable, Literal

import openai


@dataclass
class LLMTaskConfig:
    """LLM 任务配置。"""
    model: str
    temperature: float
    max_tokens: int
    timeout: float = 30.0
    max_retries: int = 2
    
    # 降级模型（主模型失败时使用）
    fallback_model: str | None = None


class LLMRuntimeConfig:
    """LLM 运行时全局配置。"""
    
    # 默认从环境变量读取
    _DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    _FALLBACK_MODEL = os.getenv("OPENAI_FALLBACK_MODEL", "gpt-4o-mini")
    
    @classmethod
    def get_default_configs(cls) -> dict[str, LLMTaskConfig]:
        """获取默认任务配置。"""
        return {
            "chat": LLMTaskConfig(
                model=cls._DEFAULT_MODEL,
                temperature=0.7,
                max_tokens=800,
                timeout=45.0,
                max_retries=2,
                fallback_model=cls._FALLBACK_MODEL,
            ),
            "intent": LLMTaskConfig(
                model=cls._FALLBACK_MODEL,
                temperature=0.2,
                max_tokens=400,
                timeout=20.0,
                max_retries=1,
                fallback_model=None,
            ),
            "review": LLMTaskConfig(
                model=cls._FALLBACK_MODEL,
                temperature=0.1,
                max_tokens=500,
                timeout=20.0,
                max_retries=1,
                fallback_model=None,
            ),
            "tool": LLMTaskConfig(
                model=cls._DEFAULT_MODEL,
                temperature=0.3,
                max_tokens=600,
                timeout=30.0,
                max_retries=2,
                fallback_model=cls._FALLBACK_MODEL,
            ),
            "planning": LLMTaskConfig(
                model=cls._FALLBACK_MODEL,
                temperature=0.3,
                max_tokens=600,
                timeout=30.0,
                max_retries=2,
                fallback_model=None,
            ),
        }


class LLMRuntime:
    """统一 LLM 运行时。
    
    用法：
        runtime = LLMRuntime()
        
        # 简单调用
        result = await runtime.call("intent", messages=[...])
        
        # 带重试和降级的调用
        result = await runtime.call_with_fallback("chat", messages=[...])
        
        # 流式调用
        async for chunk in runtime.stream("chat", messages=[...]):
            yield chunk
    """
    
    def __init__(
        self,
        configs: dict[str, LLMTaskConfig] | None = None,
        api_key: str = "",
        base_url: str = "",
    ):
        """初始化运行时。
        
        Args:
            configs: 任务类型配置，不传则使用默认
            api_key: API key，不传则从环境变量读取
            base_url: API base URL，不传则从环境变量读取
        """
        self.configs = configs or LLMRuntimeConfig.get_default_configs()
        
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        self.base_url = base_url or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        
        if not self.api_key:
            # 尝试其他 key
            self.api_key = os.getenv("MEMORY_LLM_API_KEY", "")
            if self.api_key:
                self.base_url = os.getenv("MEMORY_LLM_URL", self.base_url)
        
        self._client: openai.AsyncOpenAI | None = None
        self._init_client()
        
        # 简单日志
        self._logger = _SimpleLogger()
    
    def _init_client(self) -> None:
        """初始化 OpenAI 客户端。"""
        if self.api_key:
            self._client = openai.AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=60.0,
            )
    
    def _get_config(self, task_type: str) -> LLMTaskConfig:
        """获取任务配置。"""
        return self.configs.get(task_type, self.configs["chat"])
    
    async def call(
        self,
        task_type: str,
        messages: list[dict[str, str]],
        override_config: dict[str, Any] | None = None,
    ) -> str:
        """调用 LLM，返回文本结果。
        
        Args:
            task_type: 任务类型（chat/intent/review/tool/planning）
            messages: 消息列表
            override_config: 临时覆盖配置
            
        Returns:
            LLM 生成的文本
        """
        config = self._get_config(task_type)
        
        if override_config:
            config = LLMTaskConfig(
                model=override_config.get("model", config.model),
                temperature=override_config.get("temperature", config.temperature),
                max_tokens=override_config.get("max_tokens", config.max_tokens),
                timeout=override_config.get("timeout", config.timeout),
                max_retries=override_config.get("max_retries", config.max_retries),
            )
        
        return await self._call_with_retry(config, messages)
    
    async def _call_with_retry(
        self,
        config: LLMTaskConfig,
        messages: list[dict[str, str]],
    ) -> str:
        """带重试的调用。"""
        last_error: Exception | None = None
        
        for attempt in range(config.max_retries + 1):
            try:
                start_time = time.monotonic()
                
                if not self._client:
                    raise RuntimeError("LLM client not initialized")
                
                response = await self._client.chat.completions.create(
                    model=config.model,
                    messages=messages,
                    temperature=config.temperature,
                    max_tokens=config.max_tokens,
                    timeout=config.timeout,
                )
                
                duration = time.monotonic() - start_time
                content = response.choices[0].message.content or ""
                
                self._logger.log_call(
                    model=config.model,
                    duration=duration,
                    input_tokens=response.usage.prompt_tokens if response.usage else 0,
                    output_tokens=response.usage.completion_tokens if response.usage else 0,
                    success=True,
                )
                
                return content.strip()
                
            except Exception as exc:
                last_error = exc
                self._logger.log_call(
                    model=config.model,
                    duration=0,
                    input_tokens=0,
                    output_tokens=0,
                    success=False,
                    error=str(exc),
                )
                
                if attempt < config.max_retries:
                    await asyncio.sleep(0.5 * (attempt + 1))
                    continue
        
        # 如果主模型失败且配置了降级模型，尝试降级
        if config.fallback_model and config.fallback_model != config.model:
            try:
                fallback_config = LLMTaskConfig(
                    model=config.fallback_model,
                    temperature=config.temperature,
                    max_tokens=config.max_tokens,
                    timeout=config.timeout,
                    max_retries=0,
                )
                return await self._call_with_retry(fallback_config, messages)
            except Exception:
                pass
        
        raise RuntimeError(f"LLM call failed after {config.max_retries} retries: {last_error}")
    
    async def call_with_fallback(
        self,
        task_type: str,
        messages: list[dict[str, str]],
        fallback_fn: Callable[[], str] | None = None,
    ) -> str:
        """调用 LLM，如果失败则执行降级函数。
        
        Args:
            task_type: 任务类型
            messages: 消息列表
            fallback_fn: 降级函数，LLM 失败时调用
        """
        try:
            return await self.call(task_type, messages)
        except Exception as exc:
            self._logger.log_fallback(task_type, str(exc))
            
            if fallback_fn:
                return fallback_fn()
            
            raise
    
    async def stream(
        self,
        task_type: str,
        messages: list[dict[str, str]],
    ) -> AsyncIterator[str]:
        """流式调用 LLM。
        
        Yields:
            文本片段
        """
        config = self._get_config(task_type)
        
        if not self._client:
            raise RuntimeError("LLM client not initialized")
        
        try:
            response = await self._client.chat.completions.create(
                model=config.model,
                messages=messages,
                temperature=config.temperature,
                max_tokens=config.max_tokens,
                timeout=config.timeout,
                stream=True,
            )
            
            async for chunk in response:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta
                    
        except Exception as exc:
            self._logger.log_call(
                model=config.model,
                duration=0,
                input_tokens=0,
                output_tokens=0,
                success=False,
                error=str(exc),
            )
            raise
    
    async def call_structured(
        self,
        task_type: str,
        messages: list[dict[str, str]],
        response_format: type,
    ) -> dict[str, Any]:
        """调用 LLM 并解析结构化 JSON 输出。
        
        Args:
            task_type: 任务类型
            messages: 消息列表
            response_format: 期望的 JSON 结构类
            
        Returns:
            解析后的字典
        """
        config = self._get_config(task_type)
        
        # 在 system prompt 中要求 JSON 输出
        has_system = any(m.get("role") == "system" for m in messages)
        if not has_system:
            messages.insert(0, {"role": "system", "content": "请只输出 JSON，不要有其他文字。"})
        
        text = await self.call(task_type, messages, override_config={
            "temperature": min(config.temperature, 0.2),
            "max_tokens": config.max_tokens,
        })
        
        # 提取 JSON
        json_start = text.find("{")
        json_end = text.rfind("}")
        
        if json_start >= 0 and json_end > json_start:
            try:
                return json.loads(text[json_start:json_end + 1])
            except json.JSONDecodeError:
                pass
        
        # 如果解析失败，返回空字典
        return {}


class _SimpleLogger:
    """简单日志记录器。"""
    
    def __init__(self):
        self.call_count = 0
        self.error_count = 0
        self.total_latency = 0.0
    
    def log_call(
        self,
        model: str,
        duration: float,
        input_tokens: int,
        output_tokens: int,
        success: bool,
        error: str = "",
    ) -> None:
        """记录一次调用。"""
        self.call_count += 1
        self.total_latency += duration
        
        if not success:
            self.error_count += 1
            # 简单打印错误日志
            print(f"[LLM Error] model={model} error={error[:100]}")
    
    def log_fallback(self, task_type: str, error: str) -> None:
        """记录降级事件。"""
        print(f"[LLM Fallback] task={task_type} error={error[:100]}")
    
    def get_stats(self) -> dict[str, Any]:
        """获取统计信息。"""
        avg_latency = self.total_latency / max(self.call_count, 1)
        return {
            "call_count": self.call_count,
            "error_count": self.error_count,
            "error_rate": self.error_count / max(self.call_count, 1),
            "avg_latency": round(avg_latency, 3),
        }


# 全局运行时实例
_global_runtime: LLMRuntime | None = None


def get_llm_runtime() -> LLMRuntime:
    """获取全局 LLM 运行时实例。"""
    global _global_runtime
    if _global_runtime is None:
        _global_runtime = LLMRuntime()
    return _global_runtime


def set_llm_runtime(runtime: LLMRuntime) -> None:
    """设置全局 LLM 运行时实例。"""
    global _global_runtime
    _global_runtime = runtime


import asyncio
