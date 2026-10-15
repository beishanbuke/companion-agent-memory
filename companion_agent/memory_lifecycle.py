"""
Memory lifecycle management for companion memory.

This layer keeps lifecycle decisions outside the core memory engine. It derives
freshness, confidence, and injectability from the adapter context and the memory
snapshot, then filters or reorders memories before prompt injection.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any


TIER_DECAY_START_DAYS = {
    "profile": 180,
    "preferences": 90,
    "long_term_goals": 60,
    "episodic_events": 30,
    "safety_notes": None,
}

TIER_PRIORITY = {
    "profile": 1.0,
    "preferences": 0.9,
    "long_term_goals": 0.8,
    "safety_notes": 0.75,
    "episodic_events": 0.6,
}

HISTORY_QUERY_MARKERS = {
    "以前", "之前", "过去", "原来", "曾经", "变化", "变过", "历史",
    "还记得", "remember", "used to", "before", "previously", "history",
}


@dataclass
class LifecycleMetadata:
    """Derived lifecycle metadata for one memory item."""

    lifecycle_state: str
    confidence: float
    freshness: float
    evidence_count: int
    last_seen_at: str
    last_used_at: str
    replaced_by: str | None
    lifecycle_reason: str
    injectable: bool
    final_score: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class MemoryLifecycleManager:
    """Applies lifecycle rules to tiered memory context."""

    BLOCKED_STATES = {"deleted", "contradicted"}

    def __init__(self, reference_time: datetime | None = None):
        self.reference_time = reference_time or datetime.now(timezone.utc)

    def apply(
        self,
        context: Any,
        snapshot: dict[str, Any],
        query: str = "",
        situation: str = "casual_chat",
    ) -> dict[str, list[dict[str, Any]]]:
        """Filter/reorder context in place and return lifecycle trace."""
        allow_historical = self._allows_historical(query, situation)
        trace: dict[str, list[dict[str, Any]]] = {
            "profile": [],
            "preferences": [],
            "long_term_goals": [],
            "episodic_events": [],
            "safety_notes": [],
        }

        context.profile, trace["profile"] = self._process_mapping(
            tier="profile",
            values=context.profile,
            snapshot=snapshot,
            allow_historical=allow_historical,
        )
        context.preferences, trace["preferences"] = self._process_mapping(
            tier="preferences",
            values=context.preferences,
            snapshot=snapshot,
            allow_historical=allow_historical,
        )
        context.long_term_goals, trace["long_term_goals"] = self._process_list(
            tier="long_term_goals",
            values=context.long_term_goals,
            allow_historical=allow_historical,
        )
        context.episodic_events, trace["episodic_events"] = self._process_list(
            tier="episodic_events",
            values=context.episodic_events,
            allow_historical=allow_historical,
        )
        context.safety_notes, trace["safety_notes"] = self._process_list(
            tier="safety_notes",
            values=context.safety_notes,
            allow_historical=allow_historical,
        )
        context.memory_count = (
            len(context.profile)
            + len(context.preferences)
            + len(context.long_term_goals)
            + len(context.episodic_events)
            + len(context.safety_notes)
        )
        context.lifecycle_trace = trace
        return trace

    def _process_mapping(
        self,
        tier: str,
        values: dict[str, Any],
        snapshot: dict[str, Any],
        allow_historical: bool,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        scored: list[tuple[str, Any, LifecycleMetadata]] = []
        trace = []
        for key, value in values.items():
            source = self._mapping_source(tier, key, snapshot)
            metadata = self.evaluate_item(
                tier=tier,
                item=source,
                allow_historical=allow_historical,
            )
            trace.append({"key": key, "value": value, **metadata.to_dict()})
            if source.get("source_memory_id"):
                trace[-1]["memory_id"] = source.get("source_memory_id")
            if metadata.injectable:
                scored.append((key, value, metadata))

        scored.sort(key=lambda item: item[2].final_score, reverse=True)
        return {key: value for key, value, _ in scored}, trace

    def _process_list(
        self,
        tier: str,
        values: list[dict[str, Any]],
        allow_historical: bool,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        scored = []
        trace = []
        for index, item in enumerate(values):
            metadata = self.evaluate_item(
                tier=tier,
                item=item if isinstance(item, dict) else {},
                allow_historical=allow_historical,
            )
            label = ""
            if isinstance(item, dict):
                label = item.get("summary") or item.get("description") or item.get("note") or ""
            trace_item = {"index": index, "label": label, **metadata.to_dict()}
            if isinstance(item, dict) and item.get("memory_id"):
                trace_item["memory_id"] = item.get("memory_id")
            trace.append(trace_item)
            if metadata.injectable:
                scored.append((item, metadata))

        scored.sort(key=lambda item: item[1].final_score, reverse=True)
        return [item for item, _ in scored], trace

    def evaluate_item(
        self,
        tier: str,
        item: dict[str, Any],
        allow_historical: bool = False,
    ) -> LifecycleMetadata:
        """Derive lifecycle metadata for one item."""
        raw_status = str(item.get("lifecycle_state") or item.get("status") or "active")
        state = self._normalize_state(raw_status)
        confidence = self._confidence(tier, item)
        evidence_count = self._evidence_count(item)
        last_seen_at = self._last_seen_at(item)
        freshness = self._freshness(tier, last_seen_at)

        reason = "active_memory"
        if state in self.BLOCKED_STATES:
            injectable = False
            reason = f"{state}_memory"
        elif state == "historical" and not allow_historical:
            injectable = False
            reason = "historical_memory_hidden_for_current_query"
        else:
            injectable = True
            if state == "historical":
                reason = "historical_memory_allowed_by_query"
            elif state == "stale" or freshness < 0.35:
                state = "stale"
                reason = "low_freshness"

        final_score = self._final_score(tier, confidence, freshness, state)
        return LifecycleMetadata(
            lifecycle_state=state,
            confidence=confidence,
            freshness=freshness,
            evidence_count=evidence_count,
            last_seen_at=last_seen_at,
            last_used_at=str(item.get("last_used_at") or ""),
            replaced_by=item.get("replaced_by"),
            lifecycle_reason=reason,
            injectable=injectable,
            final_score=final_score,
        )

    def _mapping_source(self, tier: str, key: str, snapshot: dict[str, Any]) -> dict[str, Any]:
        if tier == "profile":
            slot = snapshot.get("persona_slots", {}).get(key, {})
            return slot if isinstance(slot, dict) else {"value": slot}

        if tier == "preferences":
            slot = snapshot.get("preference_slots", {}).get(key, {})
            source = dict(slot) if isinstance(slot, dict) else {"value": slot}
            profile_items = [
                item for item in snapshot.get("preference_profiles", {}).get(key, [])
                if isinstance(item, dict)
            ]
            if profile_items:
                active_items = [
                    item for item in profile_items
                    if self._normalize_state(str(item.get("status", "active"))) == "active"
                ]
                evidence = sum(self._evidence_count(item) for item in active_items or profile_items)
                source["evidence_count"] = max(source.get("evidence_count", 0), evidence)
                latest = max(
                    (self._last_seen_at(item) for item in profile_items),
                    default="",
                )
                if latest and not source.get("updated_at"):
                    source["updated_at"] = latest
            return source

        return {}

    def _normalize_state(self, status: str) -> str:
        normalized = status.lower()
        if normalized in {"active", "stale", "historical", "contradicted", "deleted"}:
            return normalized
        if normalized in {"inactive", "archived", "old"}:
            return "historical"
        if normalized in {"removed", "forgotten"}:
            return "deleted"
        return "active"

    def _confidence(self, tier: str, item: dict[str, Any]) -> float:
        raw = item.get("confidence")
        if isinstance(raw, (int, float)):
            return self._clamp(float(raw))

        defaults = {
            "profile": 0.9,
            "preferences": 0.8,
            "long_term_goals": 0.75,
            "episodic_events": 0.7,
            "safety_notes": 0.9,
        }
        confidence = defaults.get(tier, 0.7)
        evidence_count = self._evidence_count(item)
        if evidence_count > 1:
            confidence += min(0.2, 0.05 * (evidence_count - 1))
        return self._clamp(confidence)

    def _evidence_count(self, item: dict[str, Any]) -> int:
        raw = item.get("evidence_count")
        if isinstance(raw, int):
            return max(1, raw)
        if isinstance(raw, float):
            return max(1, int(raw))
        return 1

    def _last_seen_at(self, item: dict[str, Any]) -> str:
        for key in ("last_seen_at", "updated_at", "date", "created_at"):
            value = item.get(key)
            if value:
                return str(value)
        return ""

    def _freshness(self, tier: str, last_seen_at: str) -> float:
        decay_start = TIER_DECAY_START_DAYS.get(tier)
        if decay_start is None:
            return 1.0
        seen_at = self._parse_datetime(last_seen_at)
        if seen_at is None:
            return 0.8
        days_old = max(0.0, (self.reference_time - seen_at).total_seconds() / 86400)
        if days_old <= decay_start:
            return 1.0
        decay_window = max(1, decay_start * 2)
        return self._clamp(1.0 - ((days_old - decay_start) / decay_window), lower=0.1)

    def _parse_datetime(self, value: str) -> datetime | None:
        if not value:
            return None
        normalized = value.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def _final_score(self, tier: str, confidence: float, freshness: float, state: str) -> float:
        tier_priority = TIER_PRIORITY.get(tier, 0.5)
        score = 0.5 + confidence * 0.2 + freshness * 0.2 + tier_priority * 0.1
        if state == "stale":
            score -= 0.15
        if state == "historical":
            score -= 0.25
        return self._clamp(score)

    def _allows_historical(self, query: str, situation: str) -> bool:
        lowered = query.lower()
        return situation == "memory_query" or any(marker in lowered for marker in HISTORY_QUERY_MARKERS)

    def _clamp(self, value: float, lower: float = 0.0, upper: float = 1.0) -> float:
        return max(lower, min(upper, value))
