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
    ) -> TieredMemoryContext:
        """Retrieve memories organized into 5 tiers.

        Args:
            query: User message or query string
            situation: Current situation category
            limit: Max memories to retrieve
            tiers: Which tiers to retrieve. If None, retrieves all.
                Options: "profile", "preferences", "long_term_goals",
                "episodic_events", "safety_notes"

        Returns:
            TieredMemoryContext with organized memories
        """
        # Use existing retrieve() for semantic search
        raw_text = ""
        if query:
            raw_text = await self._engine.retrieve(query=query, limit=limit)

        # Build snapshot for structured access
        snapshot = self._engine.snapshot()

        context = TieredMemoryContext(raw_memory_text=raw_text)

        # Default: all tiers. Otherwise only requested tiers.
        all_tiers = tiers is None

        # Tier 1: Profile (persona_slots)
        if all_tiers or "profile" in tiers:
            context.profile = self._extract_profile(snapshot)

        # Tier 2: Preferences
        if all_tiers or "preferences" in tiers:
            context.preferences = self._extract_preferences(snapshot)

        # Tier 3: Long-term goals (from events with goal tags)
        if all_tiers or "long_term_goals" in tiers:
            context.long_term_goals = self._extract_goals(snapshot)

        # Tier 4: Episodic events
        if all_tiers or "episodic_events" in tiers:
            context.episodic_events = self._extract_events(snapshot)

        # Tier 5: Safety notes
        if all_tiers or "safety_notes" in tiers:
            context.safety_notes = self._extract_safety_notes(snapshot)

        context.memory_count = (
            len(context.profile)
            + len(context.preferences)
            + len(context.long_term_goals)
            + len(context.episodic_events)
            + len(context.safety_notes)
        )

        return context

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
            "难过": "negative", "沮丧": "negative", "焦虑": "negative",
            "压力大": "negative", "累": "negative", "疲惫": "negative",
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
