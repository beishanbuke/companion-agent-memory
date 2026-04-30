from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any
from urllib import request
from urllib.parse import urljoin

PROJECT_DIR = Path(__file__).resolve().parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from memory.base import BaseMemory


class HTTPMemoryBackend(BaseMemory):
    """Bridge memory operations to the prototype demo's shared HTTP server."""

    def __init__(self, base_url: str, timeout: float = 5.0):
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    async def store(self, role: str, content: str) -> None:
        await asyncio.to_thread(
            self._request_json,
            "POST",
            "/api/memory/store",
            {"role": role, "content": content},
        )

    async def retrieve(
        self,
        query: str = "",
        filters: dict[str, Any] | None = None,
        limit: int = 6,
    ) -> str:
        payload = await asyncio.to_thread(
            self._request_json,
            "POST",
            "/api/memory/retrieve",
            {
                "query": query,
                "filters": filters,
                "limit": limit,
            },
        )
        return str(payload.get("memory_text", ""))

    async def clear(self) -> None:
        await asyncio.to_thread(self._request_json, "POST", "/api/clear-memory", {})

    async def append_transcript_message(self, role: str, content: str) -> dict[str, Any]:
        return await asyncio.to_thread(
            self._request_json,
            "POST",
            "/api/transcript/message",
            {"role": role, "content": content},
        )

    async def start_assistant_transcript(self) -> dict[str, Any]:
        return await asyncio.to_thread(
            self._request_json,
            "POST",
            "/api/transcript/assistant/start",
            {},
        )

    async def update_assistant_transcript(self, content: str) -> dict[str, Any]:
        return await asyncio.to_thread(
            self._request_json,
            "POST",
            "/api/transcript/assistant/update",
            {"content": content},
        )

    async def get_active_character_card(self) -> dict[str, Any]:
        payload = await asyncio.to_thread(
            self._request_json,
            "GET",
            "/api/cards/active",
            None,
        )
        card = payload.get("card")
        return card if isinstance(card, dict) else {}

    async def update_voice_runtime_card(
        self,
        *,
        card_id: str,
        card_name: str,
        voice_type: str,
        model: str = "",
        source: str = "voice_bot",
    ) -> dict[str, Any]:
        return await asyncio.to_thread(
            self._request_json,
            "POST",
            "/api/voice/runtime-card/update",
            {
                "card_id": card_id,
                "card_name": card_name,
                "voice_type": voice_type,
                "model": model,
                "source": source,
            },
        )

    async def get_selected_llm_config(self) -> dict[str, Any]:
        payload = await asyncio.to_thread(
            self._request_json,
            "GET",
            "/api/voice/llm-config",
            None,
        )
        return payload if isinstance(payload, dict) else {}

    def _request_json(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = urljoin(f"{self._base_url}/", path.lstrip("/"))
        body = None
        headers = {"User-Agent": "prototype-voice-bot"}
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = request.Request(url, data=body, headers=headers, method=method.upper())
        with request.urlopen(req, timeout=self._timeout) as resp:
            raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw else {}
