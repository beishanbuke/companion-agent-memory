"""LLM-assisted memory write resolution for add/update/delete/noop decisions."""

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


_SYSTEM_PROMPT = """You decide whether a candidate long-term memory should be written.

Return strict JSON with this schema:
{
  "decision": "add" | "update" | "delete" | "noop",
  "resolved_value": "final normalized value or empty string",
  "reason": "short_reason"
}

Decision rules:
- Be conservative. If the user message is ambiguous, hypothetical, uncertain, quoted, or mainly a question, return "noop".
- If the message asks the assistant to recall something, test memory, or confirm memory, return "noop".
- If the candidate value is an interrogative placeholder such as 什么 / 哪里 / 谁 / what / where / who, return "noop".
- Use "add" when there is no existing value and the user clearly states a durable fact or preference.
- Use "update" when there is an existing value and the user clearly states a new current fact or preference that supersedes it.
- Use "delete" only when the user explicitly says the old fact or preference no longer applies and gives no replacement.
- Use "noop" when the candidate only paraphrases the old memory, lacks enough evidence, or should not be stored.
- Prefer the user's original language in resolved_value.

Context-aware hints:
- The extractor may have suggested an operation based on current memory profile. Respect it unless you see clear reasons to override.
- For location/school/job changes, "update" is correct when there's an existing value.

Output JSON only. No markdown fences.
"""


@dataclass
class MemoryWriteDecision:
    decision: str
    resolved_value: str = ""
    reason: str = ""


@dataclass
class RemoteLLMMemoryWriteResolver:
    """Resolves candidate memory writes against existing slot values."""

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
        self.api_key = self.api_key or os.getenv("MEMORY_LLM_API_KEY") or ""

    def is_configured(self) -> bool:
        return bool(self.api_key)

    async def resolve(
        self,
        *,
        content: str,
        memory_type: str,
        slot_key: str,
        candidate_value: str,
        existing_value: str | None,
    ) -> MemoryWriteDecision:
        if not self.is_configured():
            return MemoryWriteDecision(decision="noop", reason="resolver_not_configured")
        return await asyncio.to_thread(
            self._resolve_sync,
            content,
            memory_type,
            slot_key,
            candidate_value,
            existing_value,
        )

    def _resolve_sync(
        self,
        content: str,
        memory_type: str,
        slot_key: str,
        candidate_value: str,
        existing_value: str | None,
    ) -> MemoryWriteDecision:
        user_payload = {
            "user_message": content,
            "candidate": {
                "memory_type": memory_type,
                "slot_key": slot_key,
                "value": candidate_value,
            },
            "existing_memory": {
                "value": existing_value or "",
            },
        }
        payload = {
            "model": self.model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
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
                decision = str(parsed.get("decision", "noop")).strip().lower()
                if decision not in {"add", "update", "delete", "noop"}:
                    decision = "noop"
                resolved_value = str(parsed.get("resolved_value", "")).strip()
                reason = str(parsed.get("reason", "")).strip()
                return MemoryWriteDecision(
                    decision=decision,
                    resolved_value=resolved_value,
                    reason=reason,
                )
            except Exception as exc:
                logger.warning(
                    f"RemoteLLMMemoryWriteResolver: resolution failed via {endpoint}: {exc}"
                )

        return MemoryWriteDecision(decision="noop", reason="resolver_failed")

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

        raise RuntimeError(f"Unexpected resolution failure: {last_error}")


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

    raise ValueError("LLM write resolver did not return a valid JSON object")
