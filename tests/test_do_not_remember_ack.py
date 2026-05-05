"""Do-not-remember warm acknowledgment tests.

Verify that boundary requests get warm, natural confirmation.
"""

import sys
from pathlib import Path

project_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_dir))

from companion_agent.v2.response_judge import ResponseJudge, JudgeResult


def test_boundary_short_reply_detected() -> None:
    """'别记这个' + '懂的' -> cold_boundary_ack issue."""
    judge = ResponseJudge()
    issues = judge._check_boundary_ack("这个别记成长期记忆", "懂的")
    assert len(issues) > 0, "Expected cold_boundary_ack for short reply"
    assert "cold_boundary_ack" in issues[0]


def test_boundary_warm_reply_passes() -> None:
    """'别记这个' + warm reply -> no issue."""
    judge = ResponseJudge()
    issues = judge._check_boundary_ack(
        "这个别记成长期记忆",
        "放心，不记这个。你就当吐槽，我接着听。"
    )
    assert len(issues) == 0, f"Unexpected issues: {issues}"


def test_boundary_normal_reply_passes() -> None:
    """'别记这个' + natural reply -> no issue."""
    judge = ResponseJudge()
    issues = judge._check_boundary_ack(
        "这个别记成长期记忆",
        "懂的，就当咱俩半夜吐槽墙。你要现在嗦螺蛳粉我绝对不告密"
    )
    assert len(issues) == 0, f"Unexpected issues: {issues}"


def test_no_boundary_no_issue() -> None:
    """Normal message -> no boundary check."""
    judge = ResponseJudge()
    issues = judge._check_boundary_ack("今天好累", "懂的，躺着吧")
    assert len(issues) == 0, f"Unexpected issues: {issues}"


def test_rule_based_rewrite_cold_boundary() -> None:
    """Rule-based rewrite should fix cold boundary reply."""
    judge = ResponseJudge()
    improved = judge._rule_based_rewrite(
        "懂的",
        ["cold_boundary_ack: 用户要求不记/不分析时回复过短或太冷"],
        "chat",
        "tone_fix",
    )
    assert "放心" in improved or "不记" in improved, f"Expected warm ack, got: {improved}"


if __name__ == "__main__":
    test_boundary_short_reply_detected()
    test_boundary_warm_reply_passes()
    test_boundary_normal_reply_passes()
    test_no_boundary_no_issue()
    test_rule_based_rewrite_cold_boundary()
    print("All do-not-remember ack tests passed!")
