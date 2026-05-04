"""Policy rules unit tests.

Verify PolicyPlanner enforces hard constraints per state.
"""

import sys
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any

project_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_dir))

from companion_agent.v2.policy_planner import PolicyPlanner, TurnPolicy
from companion_agent.v2.state_tracker import StateTracker, ConversationState
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


def _make_planner() -> PolicyPlanner:
    return PolicyPlanner()


def _make_tracker() -> StateTracker:
    return StateTracker()


def _make_thread_manager() -> ThreadManager:
    return ThreadManager()


def test_tired_no_advice() -> None:
    """"好累，不想动" → allow_advice=False."""
    planner = _make_planner()
    tracker = _make_tracker()
    threads = _make_thread_manager()
    intent = MockIntent(
        primary_intent="vent",
        emotional_state="tired",
        emotional_intensity=0.75,
        conversation_rhythm="confiding",
    )
    state = tracker.update(intent, "好累，不想动", session_id="test-tired")
    policy = planner.plan(
        intent=intent,
        state=state,
        thread_manager=threads,
        relationship_profile={},
        user_message="好累，不想动",
    )
    assert policy.allow_advice is False, f"expected allow_advice=False for tired venting, got {policy.allow_advice}"


def test_quiet_no_questions() -> None:
    """"算了，不想说了" → max_questions=0."""
    planner = _make_planner()
    tracker = _make_tracker()
    threads = _make_thread_manager()
    intent = MockIntent(
        primary_intent="quiet",
        emotional_intensity=0.4,
        conversation_rhythm="chill",
    )
    state = tracker.update(intent, "算了，不想说了", session_id="test-quiet")
    policy = planner.plan(
        intent=intent,
        state=state,
        thread_manager=threads,
        relationship_profile={},
        user_message="算了，不想说了",
    )
    assert policy.max_questions == 0, f"expected max_questions=0 for quiet, got {policy.max_questions}"


def test_light_chat_no_thread_pull() -> None:
    """"哈哈这个视频好蠢" + 有后台论文主线 → pull_mode=silent."""
    planner = _make_planner()
    tracker = _make_tracker()
    threads = _make_thread_manager()
    sid = "test-light-chat"
    # Pre-create a background pressure thread
    threads.create_thread(
        name="论文",
        thread_type="study",
        urgency_score=0.8,
        emotion_score=0.3,
        resume_tokens="论文还没写完",
        session_id=sid,
    )
    # Now create a light_chat foreground thread
    threads.create_thread(
        name="闲聊",
        thread_type="light_chat",
        urgency_score=0.2,
        emotion_score=0.1,
        resume_tokens="刷视频",
        session_id=sid,
    )
    intent = MockIntent(
        primary_intent="companion",
        emotional_intensity=0.2,
        conversation_rhythm="bantering",
    )
    state = tracker.update(intent, "哈哈这个视频好蠢", session_id=sid)
    policy = planner.plan(
        intent=intent,
        state=state,
        thread_manager=threads,
        relationship_profile={},
        user_message="哈哈这个视频好蠢",
    )
    assert policy.pull_mode == "silent", f"expected pull_mode=silent for light_chat, got {policy.pull_mode}"


def test_user_asks_review_pull_active() -> None:
    """"继续说我论文那个" → pull_mode=active."""
    planner = _make_planner()
    tracker = _make_tracker()
    threads = _make_thread_manager()
    sid = "test-review"
    threads.create_thread(
        name="论文",
        thread_type="study",
        urgency_score=0.8,
        emotion_score=0.3,
        resume_tokens="论文还没写完",
        session_id=sid,
    )
    threads.create_thread(
        name="闲聊",
        thread_type="light_chat",
        urgency_score=0.2,
        emotion_score=0.1,
        resume_tokens="聊天",
        session_id=sid,
    )
    intent = MockIntent(
        primary_intent="execute",
        emotional_intensity=0.3,
        conversation_rhythm="planning",
        task_category="study",
    )
    state = tracker.update(intent, "继续说我论文那个", session_id=sid)
    policy = planner.plan(
        intent=intent,
        state=state,
        thread_manager=threads,
        relationship_profile={},
        user_message="继续说我论文那个",
    )
    # When user explicitly asks to continue a thread, pull_mode should be active
    assert policy.pull_mode == "active", f"expected pull_mode=active when user asks review, got {policy.pull_mode}"


def test_exam_no_review_push_short() -> None:
    """"明天考试但没复习" → goal=push_one_step/task_execution, skill_verbosity=short."""
    planner = _make_planner()
    tracker = _make_tracker()
    threads = _make_thread_manager()
    intent = MockIntent(
        primary_intent="execute",
        emotional_intensity=0.6,
        conversation_rhythm="planning",
        task_category="study",
        task_urgency=0.9,
        action_receptivity=0.7,
    )
    state = tracker.update(intent, "明天考试但没复习", session_id="test-exam")
    policy = planner.plan(
        intent=intent,
        state=state,
        thread_manager=threads,
        relationship_profile={},
        user_message="明天考试但没复习",
    )
    assert policy.goal in ("push_one_step", "task_execution"), f"expected goal=push_one_step/task_execution for exam urgency, got {policy.goal}"
    assert policy.skill_verbosity in ("short", "hint"), f"expected skill_verbosity=short/hint by default, got {policy.skill_verbosity}"


if __name__ == "__main__":
    test_tired_no_advice()
    test_quiet_no_questions()
    test_light_chat_no_thread_pull()
    test_user_asks_review_pull_active()
    test_exam_no_review_push_short()
    print("All policy rule tests passed!")
