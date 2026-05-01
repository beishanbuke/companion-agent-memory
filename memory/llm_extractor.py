"""Remote LLM-backed memory candidate extraction."""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from dataclasses import dataclass
from typing import Any
from urllib import error, request

try:
    from loguru import logger
except ImportError:  # pragma: no cover - local fallback for lightweight tests
    import logging

    logger = logging.getLogger(__name__)


_SYSTEM_PROMPT = """You extract durable long-term memory candidates from a single user message.

Return strict JSON with this schema:
{
  "candidates": [
    {
      "memory_type": "persona" | "preference" | "event",
      "slot_key": "snake_case_or_null",
      "value": "normalized memory value",
      "summary": "short summary",
      "tags": ["tag1", "tag2"],
      "metadata": {"optional": "fields"},
      "operation": "add" | "update" | "noop"
    }
  ]
}

Context-aware rules:
- You are given the user's CURRENT memory profile. Use it to decide if new info should ADD a new field or UPDATE an existing one.
- If user mentions a location/school/company change (e.g., "搬到南沙", "在港科大广州读硕士"), this is an UPDATE to existing location/education fields, not a new event.
- If user states a new fact that CONTRADICTS an existing memory (e.g., new job, new city, new school), mark operation="update" and provide the new value.
- If user states a new fact that does NOT exist yet, mark operation="add".
- If the message is just a question, greeting, or doesn't contain durable facts, return {"candidates": []}.
- For location/city changes: update home_city, work_city, or current_location.
- For education changes: update education, school, or degree.
- For job changes: update occupation or work_context.

Standard rules:
- Extract only information likely to matter across future sessions.
- Ignore pleasantries, filler, and generic reactions.
- Preserve the user's original language in `value` whenever possible. Do not translate slot values unless necessary.
- For persona/preference, prefer stable slot keys such as:
  name, age, occupation, work_context, relationship_status, home_city, work_city, current_location, education, school, degree,
  favorite_beverage, favorite_food, food_spice, food_flavor, music_style,
  activity_style, social_style, living_preference, long_term_goal, ongoing_issue,
  support_preference, boundary.
- IMPORTANT: When user mentions music preferences (e.g., "我喜欢摇滚", "我爱听爵士", "常听民谣"), ALWAYS extract as:
  memory_type: "preference"
  slot_key: "music_style"
  value: the specific genre mentioned (e.g., "摇滚", "爵士", "民谣")
- Use slot_key = null for event memories.
- If nothing durable should be stored, return {"candidates": []}.
- Output JSON only. No markdown fences.

Current user memory profile:
{existing_memory}
"""


@dataclass
class RemoteLLMMemoryExtractor:
    """Extracts memory candidates from a remote OpenAI-compatible endpoint."""

    endpoint: str = ""
    model: str = ""
    api_key: str = ""
    timeout_s: float = 12.0
    max_retries: int = 2

    def __post_init__(self) -> None:
        self.endpoint = (
            self.endpoint
            or os.getenv("MEMORY_LLM_URL")
            or "https://api2.aigcbest.top/v1/chat/completions"
        )
        self.model = self.model or os.getenv("MEMORY_LLM_MODEL") or "gpt-4o-mini"
        self.api_key = (
            self.api_key
            or os.getenv("MEMORY_LLM_API_KEY")
            or ""
        )

    def is_configured(self) -> bool:
        return bool(self.api_key)

    async def extract(self, content: str, existing_memory: str = "") -> list[dict[str, Any]]:
        if not self.is_configured():
            return []
        return await asyncio.to_thread(self._extract_sync, content, existing_memory)

    def _extract_sync(self, content: str, existing_memory: str = "") -> list[dict[str, Any]]:
        system_prompt = _SYSTEM_PROMPT.replace(
            "{existing_memory}", existing_memory or "No existing memory."
        )
        payload = {
            "model": self.model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": content},
            ],
        }

        for endpoint in self._endpoint_candidates():
            try:
                response = self._post_json(endpoint, payload)
                message = (
                    response.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                )
                parsed = _parse_json_object(message)
                candidates = parsed.get("candidates", [])
                if isinstance(candidates, list):
                    return [item for item in candidates if isinstance(item, dict)]
                return []
            except Exception as exc:
                logger.warning(
                    f"RemoteLLMMemoryExtractor: extraction failed via {endpoint}: {exc}"
                )

        return []

    def _endpoint_candidates(self) -> list[str]:
        endpoints = [self.endpoint]
        if self.endpoint.endswith("/chat/completion"):
            endpoints.append(self.endpoint + "s")
        return endpoints

    def _post_json(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            body = json.dumps(payload).encode("utf-8")
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
                with request.urlopen(req, timeout=self.timeout_s) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except error.HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace")
                raise RuntimeError(f"HTTP {exc.code}: {body}") from exc
            except Exception as exc:
                last_error = exc
                if attempt < self.max_retries:
                    time.sleep(0.6 * (attempt + 1))
                    continue
                raise

        raise RuntimeError(f"Unexpected extraction failure: {last_error}")


def _parse_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and start < end:
        parsed = json.loads(cleaned[start : end + 1])
        if isinstance(parsed, dict):
            return parsed

    raise ValueError("LLM extractor did not return a valid JSON object")
