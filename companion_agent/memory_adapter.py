"""
Memory Layer Adapter

Maps StructuredLongTermMemory into a 5-tier companion memory model:
- profile: Stable user facts (persona_slots)
- preferences: User preferences (preference_slots + profiles)
- long_term_goals: Goals derived from events + explicit statements
- episodic_events: Event-type memories with timeline
- safety_notes: Sensitive/important tagged memories

This is an adapter - it wraps the existing memory module without modifying it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .memory_lifecycle import MemoryLifecycleManager


@dataclass
class TieredMemoryContext:
    """Structured memory context for the companion agent."""
    profile: dict[str, Any] = field(default_factory=dict)
    preferences: dict[str, Any] = field(default_factory=dict)
    long_term_goals: list[dict[str, Any]] = field(default_factory=list)
    episodic_events: list[dict[str, Any]] = field(default_factory=list)
    safety_notes: list[dict[str, Any]] = field(default_factory=list)
    raw_memory_text: str = ""  # Original retrieve() output for fallback
    memory_count: int = 0
    lifecycle_trace: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    def to_prompt_section(self) -> str:
        """Convert to a structured prompt section for LLM injection."""
        parts = []

        if self.profile:
            items = [f"  - {k}: {v}" for k, v in self.profile.items()]
            parts.append("【用户档案】\n" + "\n".join(items))

        if self.preferences:
            items = []
            for k, v in self.preferences.items():
                if isinstance(v, list):
                    items.append(f"  - {k}: {', '.join(str(x) for x in v)}")
                else:
                    items.append(f"  - {k}: {v}")
            parts.append("【用户偏好】\n" + "\n".join(items))

        if self.long_term_goals:
            items = [f"  - {g.get('description', str(g))}" for g in self.long_term_goals[:3]]
            parts.append("【长期目标】\n" + "\n".join(items))

        if self.episodic_events:
            items = []
            for e in self.episodic_events[:5]:
                desc = e.get("summary") or e.get("description") or str(e)
                date = e.get("date") or e.get("updated_at", "")
                if date:
                    items.append(f"  - [{date}] {desc}")
                else:
                    items.append(f"  - {desc}")
            parts.append("【近期事件】\n" + "\n".join(items))

        if self.safety_notes:
            items = [f"  - {s.get('note', str(s))}" for s in self.safety_notes]
            parts.append("【注意事项】\n" + "\n".join(items))

        return "\n\n".join(parts) if parts else ""


class MemoryLayerAdapter:
    """Adapter that maps StructuredLongTermMemory to 5-tier companion model."""

    # Tags that indicate safety-sensitive memories
    SAFETY_TAGS = {
        "safety", "crisis", "emergency", "health", "mental_health",
        "depression", "suicide", "self_harm", "violence", "abuse",
        "敏感", "安全", "危机", "健康", "心理", "抑郁", "自残", "暴力",
    }

    # Tags that indicate goals/intentions
    GOAL_TAGS = {
        "goal", "objective", "plan", "target", "aim", "resolution",
        "目标", "计划", "打算", "决心", "愿望",
    }

    # Tags that indicate events
    EVENT_TAGS = {
        "event", "experience", "happened", "occurred", "milestone",
        "事件", "经历", "发生", "里程碑",
    }

    QUERY_SLOT_HINTS = {
        "profile": {
            "name": {"名字", "姓名", "叫什么", "叫啥", "name"},
            "home_city": {"住", "城市", "哪里", "哪儿", "广州", "上海", "杭州", "live", "city"},
            "work_city": {"工作城市", "学习城市", "上班", "上学", "学校", "工作", "work", "study"},
            "occupation": {"做什么", "职业", "工作", "身份", "occupation", "job"},
            "work_context": {"工作", "学校", "公司", "项目", "work", "school"},
            "relationship_status": {"关系", "对象", "结婚", "伴侣", "relationship"},
        },
        "preferences": {
            "favorite_beverage": {"喝", "饮料", "饮品", "咖啡", "拿铁", "美式", "甜", "beverage", "drink"},
            "favorite_food": {"吃", "食物", "饭", "菜", "food"},
            "food_spice": {"辣", "spicy"},
            "food_flavor": {"口味", "甜", "咸", "酸", "flavor"},
            "music_style": {"音乐", "歌", "听", "music"},
            "activity_style": {"运动", "散步", "活动", "羽毛球", "篮球", "activity"},
            "social_style": {"陪", "安慰", "说话", "热闹", "安静", "压力", "social"},
            "living_preference": {"住", "居住", "环境", "living"},
        },
    }

    def __init__(self, memory_engine: Any):
        """Initialize with existing memory engine.

        Args:
            memory_engine: An instance of StructuredLongTermMemory or compatible.
        """
        self._engine = memory_engine

    async def retrieve_tiered(
        self,
        query: str = "",
        situation: str = "casual_chat",
        limit: int = 10,
        tiers: list[str] | None = None,
        max_per_tier: dict[str, int] | None = None,
        apply_lifecycle: bool = True,
    ) -> TieredMemoryContext:
        """Retrieve memories organized into 5 tiers.

        Args:
            query: User message or query string
            situation: Current situation category
            limit: Max memories to retrieve

        Returns:
            TieredMemoryContext with organized memories
        """
        # Use existing retrieve() for semantic search
        raw_text = ""
        if query:
            raw_text = await self._engine.retrieve(query=query, limit=limit)

        selected_tiers = set([
            "profile",
            "preferences",
            "long_term_goals",
            "episodic_events",
            "safety_notes",
        ] if tiers is None else tiers)
        per_tier_limits = max_per_tier or {}

        # Build snapshot for structured access
        snapshot = self._engine.snapshot()

        context = TieredMemoryContext(raw_memory_text=raw_text)

        # Tier 1: Profile (persona_slots)
        if "profile" in selected_tiers:
            context.profile = self._limit_mapping(
                self._rank_mapping(
                    "profile",
                    self._extract_profile(snapshot),
                    query=query,
                ),
                per_tier_limits.get("profile"),
            )

        # Tier 2: Preferences
        if "preferences" in selected_tiers:
            context.preferences = self._limit_mapping(
                self._rank_mapping(
                    "preferences",
                    self._extract_preferences(snapshot),
                    query=query,
                ),
                per_tier_limits.get("preferences"),
            )

        # Tier 3: Long-term goals (from events with goal tags)
        if "long_term_goals" in selected_tiers:
            goals = self._rank_list("long_term_goals", self._extract_goals(snapshot), query=query)
            goal_limit = per_tier_limits.get("long_term_goals")
            context.long_term_goals = goals[:goal_limit] if goal_limit else goals

        # Tier 4: Episodic events
        if "episodic_events" in selected_tiers:
            events = self._rank_list("episodic_events", self._extract_events(snapshot), query=query)
            event_limit = per_tier_limits.get("episodic_events")
            context.episodic_events = events[:event_limit] if event_limit else events

        # Tier 5: Safety notes
        if "safety_notes" in selected_tiers:
            notes = self._rank_list("safety_notes", self._extract_safety_notes(snapshot), query=query)
            note_limit = per_tier_limits.get("safety_notes")
            context.safety_notes = notes[:note_limit] if note_limit else notes

        if apply_lifecycle:
            MemoryLifecycleManager().apply(
                context=context,
                snapshot=snapshot,
                query=query,
                situation=situation,
            )

        context.memory_count = (
            len(context.profile)
            + len(context.preferences)
            + len(context.long_term_goals)
            + len(context.episodic_events)
            + len(context.safety_notes)
        )

        tier_order = list(tiers) if tiers is not None else [
            "profile", "preferences", "long_term_goals", "episodic_events", "safety_notes"
        ]
        self._apply_total_limit(context, limit, tier_order)

        return context

    def _apply_total_limit(
        self, context: TieredMemoryContext, limit: int, tier_order: list[str]
    ) -> None:
        """Apply a global budget while preserving router tier priority."""
        if limit <= 0 or context.memory_count <= limit:
            return
        remaining = limit
        mapping_tiers = {"profile", "preferences"}
        for tier in tier_order:
            values = getattr(context, tier, None)
            if values is None:
                continue
            if tier in mapping_tiers:
                selected, remaining = self._take_mapping(values, remaining)
            else:
                selected, remaining = self._take_list(values, remaining)
            setattr(context, tier, selected)
        selected_tiers = set(tier_order)
        for tier in ["profile", "preferences", "long_term_goals", "episodic_events", "safety_notes"]:
            if tier not in selected_tiers:
                setattr(context, tier, {} if tier in mapping_tiers else [])
        context.memory_count = limit - remaining

    def _take_mapping(self, values: dict[str, Any], remaining: int) -> tuple[dict[str, Any], int]:
        selected = dict(list(values.items())[:remaining]) if remaining > 0 else {}
        return selected, remaining - len(selected)

    def _take_list(self, values: list[Any], remaining: int) -> tuple[list[Any], int]:
        selected = values[:remaining] if remaining > 0 else []
        return selected, remaining - len(selected)

    def _limit_mapping(self, values: dict[str, Any], limit: int | None) -> dict[str, Any]:
        if not limit or limit <= 0 or len(values) <= limit:
            return values
        return dict(list(values.items())[:limit])

    def _rank_mapping(self, tier: str, values: dict[str, Any], query: str = "") -> dict[str, Any]:
        if not values or not query:
            return values
        scored = [
            (key, value, self._relevance_score(tier, key, value, query))
            for key, value in values.items()
        ]
        scored.sort(key=lambda item: (-item[2], list(values).index(item[0])))
        return {key: value for key, value, _ in scored}

    def _rank_list(self, tier: str, values: list[dict[str, Any]], query: str = "") -> list[dict[str, Any]]:
        if not values or not query:
            return values
        scored = [
            (item, self._relevance_score(tier, "", item, query))
            for item in values
        ]
        scored.sort(key=lambda item: item[1], reverse=True)
        return [item for item, _ in scored]

    def _relevance_score(self, tier: str, key: str, value: Any, query: str) -> float:
        normalized_query = str(query or "").lower()
        haystack = f"{key} {value}".lower()
        score = 0.0

        for token in self._query_tokens(normalized_query):
            if token and token in haystack:
                score += 0.25

        slot_hints = self.QUERY_SLOT_HINTS.get(tier, {}).get(key, set())
        if any(hint.lower() in normalized_query for hint in slot_hints):
            score += 1.0

        if tier == "preferences" and any(cue in normalized_query for cue in ["喝", "饮", "甜", "咖啡"]):
            score += 0.2
        if tier == "episodic_events" and any(cue in normalized_query for cue in ["最近", "上周", "这周", "为什么"]):
            score += 0.2
        if tier == "long_term_goals" and any(cue in normalized_query for cue in ["目标", "长期", "第一步", "计划"]):
            score += 0.2
        return score

    def _query_tokens(self, query: str) -> list[str]:
        tokens = [token for token in query.replace("，", " ").replace("。", " ").split() if len(token) >= 2]
        chinese_keywords = [
            "住", "城市", "做什么", "职业", "工作", "喝", "饮料", "饮品", "甜",
            "咖啡", "拿铁", "美式", "目标", "作息", "压力", "安静", "陪",
        ]
        tokens.extend(keyword for keyword in chinese_keywords if keyword in query)
        return tokens

    def _extract_profile(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        """Extract profile tier from persona_slots."""
        profile = {}
        persona_slots = snapshot.get("persona_slots", {})

        for key, slot in persona_slots.items():
            if isinstance(slot, dict):
                profile[key] = slot.get("value", "")
            else:
                profile[key] = str(slot)

        return profile

    def _extract_preferences(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        """Extract preferences tier from preference_slots and profiles."""
        prefs = {}

        # From preference_slots (aggregated view)
        pref_slots = snapshot.get("preference_slots", {})
        for key, slot in pref_slots.items():
            if isinstance(slot, dict):
                prefs[key] = slot.get("value", "")
            else:
                prefs[key] = str(slot)

        # From preference_profiles (granular history)
        pref_profiles = snapshot.get("preference_profiles", {})
        for category, items in pref_profiles.items():
            if not items:
                continue
            # Get active items
            active = [item for item in items if isinstance(item, dict) and item.get("status") == "active"]
            if active:
                # Build a summary of active preferences
                values = []
                for item in active[:3]:  # Limit to top 3 per category
                    val = item.get("value", "")
                    polarity = item.get("polarity", "")
                    scope = item.get("scope", "")
                    if val:
                        parts = []
                        if polarity:
                            parts.append(polarity)
                        parts.append(val)
                        if scope and scope != "global":
                            parts.append(f"[{scope}]")
                        values.append(" ".join(parts))
                if values:
                    prefs[category] = values

        return prefs

    def _extract_goals(self, snapshot: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract long-term goals from memories with goal tags."""
        goals = []
        memories = snapshot.get("memories", [])

        for memory in memories:
            if not isinstance(memory, dict):
                continue
            tags = set(memory.get("tags", []))
            if tags & self.GOAL_TAGS:
                goals.append({
                    "memory_id": memory.get("id"),
                    "description": memory.get("summary", ""),
                    "date": memory.get("updated_at", ""),
                    "status": memory.get("status", "active"),
                })

        # Also check if any persona slots look like goals
        # (e.g., "career_goal", "learning_goal")
        persona_slots = snapshot.get("persona_slots", {})
        for key, slot in persona_slots.items():
            if "goal" in key.lower() or "目标" in key:
                value = slot.get("value", "") if isinstance(slot, dict) else str(slot)
                if value:
                    goals.append({
                        "description": value,
                        "date": slot.get("updated_at", "") if isinstance(slot, dict) else "",
                        "status": "active",
                    })

        return goals

    def _extract_events(self, snapshot: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract episodic events from memory items."""
        events = []
        memories = snapshot.get("memories", [])

        for memory in memories:
            if not isinstance(memory, dict):
                continue
            # Include event-type memories and anything with event tags
            mem_type = memory.get("memory_type", "")
            tags = set(memory.get("tags", []))

            if mem_type == "event" or (tags & self.EVENT_TAGS):
                events.append({
                    "memory_id": memory.get("id"),
                    "summary": memory.get("summary", ""),
                    "description": memory.get("content", ""),
                    "date": memory.get("updated_at", ""),
                    "status": memory.get("status", "active"),
                })

        # Sort by date (newest first) and limit
        events.sort(key=lambda x: x.get("date", ""), reverse=True)
        return events[:10]

    def _extract_safety_notes(self, snapshot: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract safety-sensitive memories."""
        notes = []
        memories = snapshot.get("memories", [])

        for memory in memories:
            if not isinstance(memory, dict):
                continue
            tags = set(memory.get("tags", []))
            if tags & self.SAFETY_TAGS:
                notes.append({
                    "memory_id": memory.get("id"),
                    "note": memory.get("summary", ""),
                    "date": memory.get("updated_at", ""),
                    "severity": "high" if tags & {"crisis", "emergency", "suicide", "自残", "暴力"} else "medium",
                })

        return notes

    async def store(self, role: str, content: str) -> None:
        """Delegate to underlying memory engine."""
        await self._engine.store(role, content)

    async def delete_memory(self, memory_id: str) -> Any:
        """Delegate to underlying memory engine."""
        return await self._engine.delete_memory(memory_id)

    def get_profile_summary(self) -> dict[str, Any]:
        """Get a lightweight profile summary for persona layer."""
        snapshot = self._engine.snapshot()
        return {
            "name": snapshot.get("persona_slots", {}).get("name", {}).get("value"),
            "communication_style": snapshot.get("persona_slots", {}).get("communication_style", {}).get("value"),
            "preferences": {
                k: (v.get("value", "") if isinstance(v, dict) else str(v))
                for k, v in list(snapshot.get("preference_slots", {}).items())[:5]
            },
            "emotional_state": self._infer_emotional_state(snapshot),
        }

    def _infer_emotional_state(self, snapshot: dict[str, Any]) -> str:
        """Infer recent emotional state from events (simple heuristic)."""
        events = snapshot.get("memories", [])
        emotional_keywords = {
            "开心": "positive", "高兴": "positive", "兴奋": "positive",
            "期待": "positive", "期待中": "positive",
            "难过": "negative", "沮丧": "negative", "焦虑": "negative",
            "紧张": "negative", "愤怒": "negative", "生气": "negative",
            "孤独": "negative", "寂寞": "negative", "疲惫": "negative",
            "压力大": "negative", "累": "negative",
            "平静": "neutral", "一般": "neutral", "还好": "neutral",
        }

        for memory in reversed(events[-10:]):  # Check last 10
            if not isinstance(memory, dict):
                continue
            content = memory.get("content", "") + memory.get("summary", "")
            for keyword, sentiment in emotional_keywords.items():
                if keyword in content:
                    return sentiment

        return ""
