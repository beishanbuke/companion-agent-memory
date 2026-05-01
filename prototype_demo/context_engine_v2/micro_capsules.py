from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


@dataclass
class ContextCapsule:
    id: str
    type: Literal[
        "mood_signal", "user_preference", "habit", "scene",
        "skill_hint", "robot_action_hint", "safety_hint", "state_summary"
    ]
    content: str
    confidence: float
    priority: int
    injection_mode: Literal["none", "short_hint", "system_rule", "action_schema"] = "short_hint"
    visible_to_user: bool = False
    max_tokens: int = 60


def create_mood_capsule(mood_signal: Any) -> ContextCapsule | None:
    if not mood_signal or not mood_signal.active:
        return None
    
    subtype = mood_signal.data.get("subtype", "neutral")
    content_map = {
        "tired": "User seems tired/low-energy. Keep response short and gentle. Suggest one small action.",
        "anxious": "User seems anxious. Acknowledge feelings first. Give small next step, avoid over-planning.",
        "sad": "User seems down. Be warm and present. Don't force cheerfulness. Offer quiet company.",
        "happy": "User is in good mood. Match energy. Keep it light and fun.",
    }
    
    return ContextCapsule(
        id=f"mood_{subtype}",
        type="mood_signal",
        content=content_map.get(subtype, "User mood: neutral."),
        confidence=mood_signal.confidence,
        priority=85,
        injection_mode="short_hint",
        max_tokens=40,
    )


def create_food_capsule(food_signal: Any, user_state: dict[str, Any] | None = None) -> ContextCapsule | None:
    if not food_signal or not food_signal.active:
        return None
    
    intent = food_signal.intent
    
    if intent == "diet_routine":
        return ContextCapsule(
            id="food_diet_routine",
            type="habit",
            content="User mentions irregular eating habits. Suggest gentle routine, not strict plan. Focus on breakfast first.",
            confidence=food_signal.confidence,
            priority=78,
            injection_mode="short_hint",
            max_tokens=45,
        )
    
    # Food recommendation
    spicy = food_signal.data.get("spicy_preference", False)
    light = food_signal.data.get("light_preference", False)
    
    content = "User wants food recommendation."
    if spicy:
        content += " They like spicy food."
    if light:
        content += " They prefer lighter options."
    content += " Suggest 2-3 practical options, not restaurants."
    
    return ContextCapsule(
        id="food_recommendation",
        type="skill_hint",
        content=content,
        confidence=food_signal.confidence,
        priority=80,
        injection_mode="short_hint",
        max_tokens=35,
    )


def create_music_capsule(music_signal: Any) -> ContextCapsule | None:
    if not music_signal or not music_signal.active:
        return None
    
    vibe = music_signal.data.get("vibe", "neutral")
    detected_preferences = music_signal.data.get("detected_preferences", [])
    has_preference = music_signal.data.get("has_preference_statement", False)
    
    # If user stated music preferences, create a user_preference capsule
    if has_preference and detected_preferences:
        prefs_str = ", ".join(detected_preferences)
        return ContextCapsule(
            id="music_preference",
            type="user_preference",
            content=f"User prefers {prefs_str} music. Consider this when recommending songs or playlists.",
            confidence=music_signal.confidence,
            priority=88,  # Higher priority than skill hint
            injection_mode="short_hint",
            max_tokens=30,
        )
    
    content_map = {
        "low_energy": "User wants music, likely low-energy/chill. Recommend short playlist vibe (lo-fi, soft pop, warm R&B). Keep suggestion brief.",
        "energetic": "User wants upbeat music. Recommend energetic but not overwhelming playlist.",
        "neutral": "User wants music recommendations. Ask about mood or suggest a versatile playlist.",
    }
    
    return ContextCapsule(
        id=f"music_{vibe}",
        type="skill_hint",
        content=content_map.get(vibe, content_map["neutral"]),
        confidence=music_signal.confidence,
        priority=82,
        injection_mode="short_hint",
        max_tokens=40,
    )


def create_outfit_capsule(outfit_signal: Any) -> ContextCapsule | None:
    if not outfit_signal or not outfit_signal.active:
        return None
    
    scene = outfit_signal.data.get("scene", "unknown")
    
    content_map = {
        "formal": "User needs formal outfit advice. Keep it simple: shirt/blazer + trousers + clean shoes. Avoid over-styling.",
        "casual": "User wants casual outfit. Suggest clean, comfortable, under 3 colors. Campus-appropriate.",
        "unknown": "User asks about outfit. Suggest versatile casual look. Ask about occasion if unclear.",
    }
    
    return ContextCapsule(
        id=f"outfit_{scene}",
        type="skill_hint",
        content=content_map.get(scene, content_map["unknown"]),
        confidence=outfit_signal.confidence,
        priority=80,
        injection_mode="short_hint",
        max_tokens=35,
    )


def create_campus_capsule(campus_signal: Any) -> ContextCapsule | None:
    if not campus_signal or not campus_signal.active:
        return None
    
    location = campus_signal.data.get("location", "")
    
    content_map = {
        "library": "User mentions library. They may need study support or place alternatives.",
        "lab": "User mentions lab/coding. Potential lab-mode easter egg opportunity. Keep it fun but helpful.",
        "dorm": "User in dorm context. Suggest comfortable, low-pressure activities.",
    }
    
    return ContextCapsule(
        id=f"campus_{location}",
        type="scene",
        content=content_map.get(location, "User mentions campus location."),
        confidence=campus_signal.confidence,
        priority=75,
        injection_mode="short_hint",
        max_tokens=30,
    )


def create_robot_capsule(robot_signal: Any) -> ContextCapsule | None:
    if not robot_signal or not robot_signal.active:
        return None
    
    trigger = robot_signal.data.get("trigger", "explicit")
    action_type = robot_signal.data.get("action_type", "comfort")
    
    if trigger == "implicit":
        return ContextCapsule(
            id="robot_implicit_support",
            type="robot_action_hint",
            content="User seems to need gentle support. If robot actions available, consider soft light + calm voice. Don't mention robot unless user asks.",
            confidence=robot_signal.confidence,
            priority=70,
            injection_mode="action_schema",
            visible_to_user=False,
            max_tokens=40,
        )
    
    return ContextCapsule(
        id="robot_explicit_action",
        type="robot_action_hint",
        content="User explicitly asked for robot action. Provide action + natural language response.",
        confidence=robot_signal.confidence,
        priority=85,
        injection_mode="action_schema",
        visible_to_user=False,
        max_tokens=30,
    )


def create_easter_egg_capsule(easter_egg_signal: Any) -> ContextCapsule | None:
    if not easter_egg_signal or not easter_egg_signal.active:
        return None
    
    intent = easter_egg_signal.intent
    
    content_map = {
        "lab_mode_easter_egg": "Lab mode detected! User is coding/debugging. Switch to fun lab-companion mode. Light humor about env vars, bugs, and debugging. Keep it encouraging.",
        "food_fun_mode": "User mentioned comfort food. Match enthusiasm. Suggest one fun option with energy.",
        "youth_slang_mode": "Youth slang detected! Match their energy and language style. Keep it casual and relatable.",
    }
    
    return ContextCapsule(
        id=f"easter_egg_{intent}",
        type="skill_hint",
        content=content_map.get(intent, "Fun mode detected!"),
        confidence=easter_egg_signal.confidence,
        priority=88,  # High priority for easter eggs
        injection_mode="short_hint",
        max_tokens=40,
    )


def create_state_capsule(state_tracker: Any) -> ContextCapsule | None:
    """Create capsule from user state tracker."""
    summary = state_tracker.get_state_summary()
    if not summary or summary == "No notable state.":
        return None
    
    return ContextCapsule(
        id="user_state_summary",
        type="state_summary",
        content=f"Background state: {summary}",
        confidence=0.6,
        priority=65,
        injection_mode="short_hint",
        visible_to_user=False,
        max_tokens=30,
    )


def build_capsules_from_signals(
    signals: dict[str, Any],
    state_tracker: Any | None = None,
) -> list[ContextCapsule]:
    """Build all context capsules from signals."""
    capsules: list[ContextCapsule] = []
    
    # Mood capsule
    if "mood" in signals:
        cap = create_mood_capsule(signals["mood"])
        if cap:
            capsules.append(cap)
    
    # Food capsule
    if "food" in signals:
        cap = create_food_capsule(signals["food"])
        if cap:
            capsules.append(cap)
    
    # Music capsule
    if "music" in signals:
        cap = create_music_capsule(signals["music"])
        if cap:
            capsules.append(cap)
    
    # Outfit capsule
    if "outfit" in signals:
        cap = create_outfit_capsule(signals["outfit"])
        if cap:
            capsules.append(cap)
    
    # Campus capsule
    if "campus" in signals:
        cap = create_campus_capsule(signals["campus"])
        if cap:
            capsules.append(cap)
    
    # Robot capsule
    if "robot" in signals:
        cap = create_robot_capsule(signals["robot"])
        if cap:
            capsules.append(cap)
    
    # Easter egg capsules
    if "easter_eggs" in signals:
        for egg_signal in signals["easter_eggs"]:
            cap = create_easter_egg_capsule(egg_signal)
            if cap:
                capsules.append(cap)
    
    # State summary capsule
    if state_tracker:
        cap = create_state_capsule(state_tracker)
        if cap:
            capsules.append(cap)
    
    # Sort by priority
    capsules.sort(key=lambda c: c.priority, reverse=True)
    
    return capsules
