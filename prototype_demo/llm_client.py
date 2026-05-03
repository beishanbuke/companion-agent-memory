"""LLM Client - 简单的 LLM 调用客户端

供 context_engine_v2 新架构模块使用。
使用环境变量中的 API 配置。
"""

from __future__ import annotations

import json
import os
from typing import Any
from urllib import error, request


class LLMClient:
    """简单的 LLM 客户端"""
    
    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY", "")
        self.base_url = os.getenv("OPENAI_BASE_URL", "https://api.siliconflow.cn/v1")
        self.model = os.getenv("OPENAI_MODEL", "deepseek-ai/DeepSeek-V3")
        
        # 如果没有 OPENAI_API_KEY，尝试其他 key
        if not self.api_key:
            self.api_key = os.getenv("MEMORY_LLM_API_KEY", "")
            self.base_url = os.getenv("MEMORY_LLM_URL", self.base_url)
    
    async def complete(
        self,
        prompt: str,
        max_tokens: int = 500,
        temperature: float = 0.7,
        system_prompt: str = "你是一个 helpful assistant。",
    ) -> str:
        """完成一个 prompt"""
        
        if not self.api_key:
            raise RuntimeError("No API key configured. Set OPENAI_API_KEY or MEMORY_LLM_API_KEY in .env")
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]
        
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        
        body = json.dumps(payload).encode("utf-8")
        endpoint = f"{self.base_url.rstrip('/')}/chat/completions"
        
        req = request.Request(
            endpoint,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        
        try:
            with request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return (
                    data.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                    .strip()
                )
        except error.HTTPError as exc:
            response_text = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {exc.code}: {response_text}") from exc
        except Exception as exc:
            raise RuntimeError(f"LLM request failed: {exc}") from exc


# 全局客户端实例
_llm_client: LLMClient | None = None


def get_llm_client() -> LLMClient:
    """获取全局 LLM 客户端"""
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client
