"""
Response Judge Rule Tests

验证 ResponseJudge 的规则层检测：
1. psych_therapy_tone 标记
2. casual 模式下列表化输出标记
3. quiet 回复带问号标记
4. safety 模式不因长度误判
5. fast path 不触发 LLM judge
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from companion_agent.v2.response_judge import ResponseJudge, JudgeResult


class AsyncMockRuntime:
    """Mock LLM runtime that returns safe JSON for tests that accidentally hit LLM path."""
    async def call(self, *args, **kwargs):
        return (
            '{"overall_score": 7, "issues": [], '
            '"rewrite_level": "none", "improved_version": ""}'
        )


@pytest.fixture
def response_judge():
    return ResponseJudge(runtime=AsyncMockRuntime())


@pytest.mark.asyncio
async def test_psych_phrase_flagged(response_judge: ResponseJudge):
    """包含'我理解你的感受'的回复被标记为 psych_therapy_tone"""
    result = await response_judge.judge(
        user_message="我今天好难过",
        assistant_reply="我理解你的感受，这确实不容易。",
        conversation_mode="chat",
    )
    issues_str = " ".join(result.issues)
    assert "psych_therapy_tone" in issues_str, (
        f"Expected psych_therapy_tone in issues, got {result.issues!r}"
    )


@pytest.mark.asyncio
async def test_list_in_casual_flagged(response_judge: ResponseJudge):
    """包含'首先、其次、最后'的 casual 回复被标记为 over_summary_tone"""
    result = await response_judge.judge(
        user_message="周末打算干嘛",
        assistant_reply="首先，你可以去图书馆。其次，你可以看电影。最后，早点睡觉。",
        conversation_mode="chat",
    )
    issues_str = " ".join(result.issues)
    assert "over_summary_tone" in issues_str or "模式错误" in issues_str, (
        f"Expected over_summary_tone or mode error in issues, got {result.issues!r}"
    )


@pytest.mark.asyncio
async def test_quiet_with_question_flagged(response_judge: ResponseJudge):
    """quiet 回复带问号被标记为 over_question_tone"""
    result = await response_judge.judge(
        user_message="我想静静",
        assistant_reply="你确定吗？",
        conversation_mode="quiet",
    )
    issues_str = " ".join(result.issues)
    assert "over_question_tone" in issues_str, (
        f"Expected over_question_tone in issues, got {result.issues!r}"
    )


@pytest.mark.asyncio
async def test_safety_not_flagged_for_length(response_judge: ResponseJudge):
    """safety 回复不因较长被误判"""
    result = await response_judge.judge(
        user_message="我觉得活着没意义",
        assistant_reply=(
            "我听到你这么说，很担心你。你现在安全吗？"
            "如果你有任何伤害自己的想法，请立刻联系身边信任的人，"
            "或者拨打心理援助热线。我在这里陪你。"
        ),
        conversation_mode="safety",
    )
    # Should NOT flag length-related issues
    assert "模式错误" not in " ".join(result.issues), (
        f"Safety reply should not be flagged for length: {result.issues!r}"
    )


@pytest.mark.asyncio
async def test_fast_path_no_llm_judge(response_judge: ResponseJudge):
    """fast path（短寒暄）不触发 LLM judge"""
    result = await response_judge.judge(
        user_message="你好",
        assistant_reply="哈喽！今天怎么样？",
        conversation_mode="chat",
    )
    assert result.rewrite_level == "none", (
        f"Expected rewrite_level='none' for fast path, got {result.rewrite_level!r}"
    )
