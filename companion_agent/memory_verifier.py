"""Lightweight verification for whether a response used injected memory."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from .memory_adapter import TieredMemoryContext
from .memory_router import MemoryRouteDecision


@dataclass
class MemoryUseVerification:
    status: str
    expected_terms: list[str] = field(default_factory=list)
    matched_terms: list[str] = field(default_factory=list)
    missing_terms: list[str] = field(default_factory=list)
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class MemoryUseVerifier:
    """Rule-based post-generation verifier.

    It is intentionally lightweight: this should not block generation or call
    another model. The goal is to expose obvious misses in the debug surface.
    """

    def verify(
        self,
        *,
        user_message: str,
        assistant_reply: str,
        memory_context: TieredMemoryContext,
        memory_route: MemoryRouteDecision,
    ) -> MemoryUseVerification:
        if not memory_route.need_memory:
            return MemoryUseVerification(status="not_required", reason="route_did_not_use_memory")
        if memory_context.memory_count <= 0:
            return MemoryUseVerification(status="no_memory", reason="no_memory_injected")

        expected = self._expected_terms(user_message, memory_context, memory_route)
        if not expected:
            return MemoryUseVerification(status="unscored", reason="no_expected_terms")

        reply = str(assistant_reply or "")
        matched = [term for term in expected if term and term in reply]
        missing = [term for term in expected if term not in matched]
        if matched:
            return MemoryUseVerification(
                status="ok",
                expected_terms=expected,
                matched_terms=matched,
                missing_terms=missing,
                reason="response_mentions_relevant_memory_terms",
            )
        return MemoryUseVerification(
            status="missed",
            expected_terms=expected,
            matched_terms=[],
            missing_terms=missing,
            reason="response_did_not_reflect_injected_memory",
        )

    def _expected_terms(
        self,
        user_message: str,
        memory_context: TieredMemoryContext,
        memory_route: MemoryRouteDecision,
    ) -> list[str]:
        query = str(user_message or "")
        terms: list[str] = []

        if "profile" in memory_route.tiers:
            if any(cue in query for cue in ["住", "哪里", "哪儿", "城市"]):
                terms.extend(self._value_terms(memory_context.profile.get("home_city")))
            if any(cue in query for cue in ["做什么", "职业", "工作", "身份"]):
                terms.extend(self._value_terms(memory_context.profile.get("occupation")))
                terms.extend(self._value_terms(memory_context.profile.get("work_context")))

        if "preferences" in memory_route.tiers:
            if any(cue in query for cue in ["喝", "饮", "甜", "咖啡", "买杯"]):
                terms.extend(self._value_terms(memory_context.preferences.get("favorite_beverage")))
            if any(cue in query for cue in ["安慰", "陪", "压力", "说话"]):
                terms.extend(self._value_terms(memory_context.preferences.get("social_style")))
                terms.extend(self._value_terms(memory_context.preferences.get("general_热_闹_场")))

        if "long_term_goals" in memory_route.tiers:
            for goal in memory_context.long_term_goals[:2]:
                terms.extend(self._value_terms(goal.get("description")))

        if "episodic_events" in memory_route.tiers and any(cue in query for cue in ["最近", "上周", "这周", "赶稿"]):
            for event in memory_context.episodic_events[:2]:
                terms.extend(self._value_terms(event.get("summary") or event.get("description")))

        return self._dedupe_terms(terms)[:6]

    def _value_terms(self, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            raw = " ".join(str(item) for item in value)
        else:
            raw = str(value)
        raw = raw.replace("dislike ", "不喜欢").replace("like ", "")
        candidates = re.split(r"[；;，,\s]+", raw)
        terms = []
        for candidate in candidates:
            cleaned = candidate.strip(" 。[]()（）")
            if not cleaned:
                continue
            if cleaned.startswith("喜欢") and len(cleaned) > 2:
                terms.append(cleaned[2:])
            elif cleaned.startswith("不喜欢") and len(cleaned) > 3:
                terms.append(cleaned[3:])
            terms.append(cleaned)
        return terms

    def _dedupe_terms(self, terms: list[str]) -> list[str]:
        output: list[str] = []
        for term in terms:
            normalized = str(term or "").strip()
            if len(normalized) < 2:
                continue
            if normalized not in output:
                output.append(normalized)
        return output
