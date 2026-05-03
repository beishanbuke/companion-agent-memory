from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from datetime import datetime


@dataclass
class MoodState:
    current: str = "neutral"  # neutral, tired, anxious, sad, happy
    confidence: float = 0.0
    last_updated_at: str = ""


@dataclass
class LifestyleState:
    sleep_pattern: str = ""  # e.g., "night_owl", "early_bird", "irregular"
    diet_preference: list[str] = field(default_factory=list)
    recent_food_mentions: list[str] = field(default_factory=list)
    activity_preference: list[str] = field(default_factory=list)


@dataclass
class CompanionPreference:
    tone: str = "warm"  # warm, funny, direct, gentle
    answer_length: str = "medium"  # short, medium, detailed


@dataclass
class UserState:
    mood: MoodState = field(default_factory=MoodState)
    lifestyle: LifestyleState = field(default_factory=LifestyleState)
    companion_preference: CompanionPreference = field(default_factory=CompanionPreference)
    interests: list[str] = field(default_factory=list)
    recent_scenes: list[str] = field(default_factory=list)
    last_interaction_at: str = ""


class UserStateTracker:
    """Tracks user state across conversations."""
    
    def __init__(self):
        self._state = UserState()
    
    def update_from_signals(self, signals: dict[str, Any]) -> dict[str, Any]:
        """Update state based on detected signals. Returns state changes."""
        changes = []
        now = datetime.now().isoformat()
        
        # Update mood
        mood_signal = signals.get("mood")
        if mood_signal and mood_signal.active and mood_signal.confidence > 0.6:
            old_mood = self._state.mood.current
            new_mood = mood_signal.data.get("subtype", "neutral")
            if old_mood != new_mood:
                self._state.mood.current = new_mood
                self._state.mood.confidence = mood_signal.confidence
                self._state.mood.last_updated_at = now
                changes.append({
                    "type": "mood_update",
                    "old": old_mood,
                    "new": new_mood,
                    "confidence": mood_signal.confidence,
                })
        
        # Update food mentions
        food_signal = signals.get("food")
        if food_signal and food_signal.active:
            if "spicy" in str(food_signal.data) and "辣" not in self._state.lifestyle.diet_preference:
                self._state.lifestyle.diet_preference.append("spicy")
                changes.append({"type": "preference_update", "key": "diet", "value": "spicy"})
            
            # Track recent food mentions
            if "time_of_day" in food_signal.data:
                self._state.lifestyle.recent_food_mentions.append(now)
                if len(self._state.lifestyle.recent_food_mentions) > 10:
                    self._state.lifestyle.recent_food_mentions.pop(0)
        
        # Update scenes
        campus_signal = signals.get("campus")
        if campus_signal and campus_signal.active:
            location = campus_signal.data.get("location", "")
            if location and location not in self._state.recent_scenes:
                self._state.recent_scenes.insert(0, location)
                if len(self._state.recent_scenes) > 5:
                    self._state.recent_scenes.pop()
                changes.append({"type": "scene_update", "scene": location})
        
        self._state.last_interaction_at = now
        return {"changes": changes, "state": self.to_dict()}
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "mood": {
                "current": self._state.mood.current,
                "confidence": self._state.mood.confidence,
                "last_updated_at": self._state.mood.last_updated_at,
            },
            "lifestyle": {
                "sleep_pattern": self._state.lifestyle.sleep_pattern,
                "diet_preference": self._state.lifestyle.diet_preference,
                "recent_food_mentions_count": len(self._state.lifestyle.recent_food_mentions),
                "activity_preference": self._state.lifestyle.activity_preference,
            },
            "companion_preference": {
                "tone": self._state.companion_preference.tone,
                "answer_length": self._state.companion_preference.answer_length,
            },
            "interests": self._state.interests,
            "recent_scenes": self._state.recent_scenes,
            "last_interaction_at": self._state.last_interaction_at,
        }
    
    def get_state_summary(self) -> str:
        """Get a short state summary for context injection."""
        parts = []
        if self._state.mood.current != "neutral" and self._state.mood.confidence > 0.5:
            parts.append(f"User seems {self._state.mood.current}.")
        if self._state.recent_scenes:
            parts.append(f"Recent scenes: {', '.join(self._state.recent_scenes[:3])}.")
        if self._state.lifestyle.diet_preference:
            parts.append(f"Diet prefs: {', '.join(self._state.lifestyle.diet_preference[:3])}.")
        
        return " ".join(parts) if parts else "No notable state."
    
    def should_suggest_meal(self) -> bool:
        """Check if user might need a meal suggestion."""
        # Simple heuristic: if no recent food mentions today
        if not self._state.lifestyle.recent_food_mentions:
            return False
        
        last_mention = self._state.lifestyle.recent_food_mentions[-1]
        try:
            from datetime import datetime
            last_dt = datetime.fromisoformat(last_mention)
            now = datetime.now()
            hours_since = (now - last_dt).total_seconds() / 3600
            return hours_since > 5  # Suggest if > 5 hours since last food mention
        except:
            return False


# Per-user state tracker instances
_state_trackers: dict[str, UserStateTracker] = {}


def get_state_tracker(
    user_id: str = "demo-user",
    conversation_id: str = "default"
) -> UserStateTracker:
    key = f"{user_id}:{conversation_id}"
    if key not in _state_trackers:
        _state_trackers[key] = UserStateTracker()
    return _state_trackers[key]
