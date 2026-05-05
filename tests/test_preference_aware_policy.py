"""Preference-aware policy unit tests.

Verify PolicyPlanner respects user preferences from relationship_profile.
"""

import sys
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any

project_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_dir))

from companion_agent.v2.policy_planner import PolicyPlanner, TurnPolicy
from companion_agent.v2.state_tracker import StateTracker
from companion_agent.v2.thread_manager import ThreadManager


@dataclass
class MockIntent:
    primary_intent: str = "companion"
    emotional_state: str = "neutral"
    emotional_intensity: float = 0.3
    conversation_rhythm: str = "chill"
    task_category: str = "none"
    task_urgency: float = 0.0
    action_receptivity: float = 0.5
    topic_shift_type: str = "none"
    pressure_signal: float = 0.0
    intent_confidence: float = 0.8
    clarification_confidence: float = 0.0
    thread_candidates: list = field(default_factory=list)


@dataclass
class MockRelationshipProfile:
    """Mock relationship profile with Phase 10.1 preferences."""
    comfort_style: str = "balanced"
    banter_tolerance: float = 0.5
    advice_threshold: float = 0.5
    humor_mode: str = "light"
    dislikes_education: bool = False
    dislikes_big_plan: bool = False
    prefers_micro_action: bool = False
    dislikes_analysis: bool = False


def _make_planner() -> PolicyPlanner:
    return PolicyPlanner()


def _make_tracker() -> StateTracker:
    return StateTracker()


def _make_thread_manager() -> ThreadManager:
    return ThreadManager()


def test_dislikes_education_bans_motivational() -> None:
    """User dislikes education tone -> policy adds ban_motivational_words constraint."""
    planner = _make_planner()
    tracker = _make_tracker()
    threads = _make_thread_manager()
    intent = MockIntent(
        primary_intent="vent",
        emotional_intensity=0.6,
        conversation_rhythm="confiding",
    )
    state = tracker.update(intent, "我压力好大", session_id="test-edu")
    rel = MockRelationshipProfile(dislikes_education=True)
    policy = planner.plan(
        intent=intent,
        state=state,
        thread_manager=threads,
        relationship_profile=rel,
        user_message="我压力好大",
    )
    assert "ban_motivational_words" in policy.hard_constraints, \
        f"Expected ban_motivational_words in constraints, got {policy.hard_constraints}"


def test_dislikes_big_plan_limits_steps() -> None:
    """User dislikes big plan -> policy adds max_plan_steps_2 constraint."""
    planner = _make_planner()
    tracker = _make_tracker()
    threads = _make_thread_manager()
    intent = MockIntent(
        primary_intent="advice",
        emotional_intensity=0.3,
        conversation_rhythm="planning",
        task_category="study",
        task_urgency=0.8,
    )
    state = tracker.update(intent, "我下周全撞一起了", session_id="test-plan")
    rel = MockRelationshipProfile(dislikes_big_plan=True)
    policy = planner.plan(
        intent=intent,
        state=state,
        thread_manager=threads,
        relationship_profile=rel,
        user_message="我下周全撞一起了",
    )
    assert "max_plan_steps_2" in policy.hard_constraints, \
        f"Expected max_plan_steps_2 in constraints, got {policy.hard_constraints}"
    assert policy.skill_verbosity != "full", \
        f"Expected skill_verbosity != full when dislikes_big_plan, got {policy.skill_verbosity}"


def test_prefers_micro_action_enables_micro() -> None:
    """User prefers micro action -> allow_micro_action=True for task goals."""
    planner = _make_planner()
    tracker = _make_tracker()
    threads = _make_thread_manager()
    intent = MockIntent(
        primary_intent="execute",
        emotional_intensity=0.4,
        conversation_rhythm="planning",
        task_category="study",
        task_urgency=0.9,
    )
    state = tracker.update(intent, "明天考试但我还没复习", session_id="test-micro")
    rel = MockRelationshipProfile(prefers_micro_action=True)
    policy = planner.plan(
        intent=intent,
        state=state,
        thread_manager=threads,
        relationship_profile=rel,
        user_message="明天考试但我还没复习",
    )
    assert policy.allow_micro_action is True, \
        f"Expected allow_micro_action=True for task pressure, got {policy.allow_micro_action}"
    assert "planning_style_one_small_step" in policy.hard_constraints, \
        f"Expected planning_style_one_small_step in constraints, got {policy.hard_constraints}"


def test_dislikes_analysis_limits_questions() -> None:
    """User dislikes analysis -> max_questions <= 1."""
    planner = _make_planner()
    tracker = _make_tracker()
    threads = _make_thread_manager()
    intent = MockIntent(
        primary_intent="advice",
        emotional_intensity=0.3,
        conversation_rhythm="planning",
        task_category="study",
    )
    state = tracker.update(intent, "帮我看看这个", session_id="test-analysis")
    rel = MockRelationshipProfile(dislikes_analysis=True)
    policy = planner.plan(
        intent=intent,
        state=state,
        thread_manager=threads,
        relationship_profile=rel,
        user_message="帮我看看这个",
    )
    assert policy.max_questions <= 1, \
        f"Expected max_questions <= 1 when dislikes_analysis, got {policy.max_questions}"
    assert "avoid_psychological_framing" in policy.hard_constraints, \
        f"Expected avoid_psychological_framing in constraints, got {policy.hard_constraints}"


def test_no_preference_no_extra_constraints() -> None:
    """No preference set -> no extra constraints added."""
    planner = _make_planner()
    tracker = _make_tracker()
    threads = _make_thread_manager()
    intent = MockIntent(
        primary_intent="advice",
        emotional_intensity=0.3,
        conversation_rhythm="planning",
        task_category="study",
    )
    state = tracker.update(intent, "帮我看看这个", session_id="test-none")
    rel = MockRelationshipProfile()  # all defaults False
    policy = planner.plan(
        intent=intent,
        state=state,
        thread_manager=threads,
        relationship_profile=rel,
        user_message="帮我看看这个",
    )
    extra_constraints = {
        "ban_motivational_words",
        "max_plan_steps_2",
        "planning_style_one_small_step",
        "avoid_psychological_framing",
    }
    assert not extra_constraints.intersection(set(policy.hard_constraints)), \
        f"Unexpected extra constraints: {set(policy.hard_constraints) & extra_constraints}"


if __name__ == "__main__":
    test_dislikes_education_bans_motivational()
    test_dislikes_big_plan_limits_steps()
    test_prefers_micro_action_enables_micro()
    test_dislikes_analysis_limits_questions()
    test_no_preference_no_extra_constraints()
    print("All preference-aware policy tests passed!")
