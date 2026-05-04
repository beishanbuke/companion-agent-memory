"""
Life Skill Verbosity Tests

验证生活技能返回的建议 verbosity 控制：
1. 饮食建议简洁性（不超过 60 字）
2. 情绪饮食建议不含预算/搜索词
3. 学习计划不超过 3 步
4. 详细计划 verbosity 为 card 或 full
5. 社交回复至少 2 个可复制选项
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from companion_agent.v2.life_skills import DietSkill, StudySkill, SocialSkill
from companion_agent.v2.life_skills import study_plan_skill
from companion_agent.v2.skill_contracts import SkillInput


@pytest.fixture
def diet_skill():
    return DietSkill()


@pytest.fixture
def study_skill():
    return StudySkill()


@pytest.fixture
def social_skill():
    return SocialSkill()


@pytest.mark.asyncio
async def test_food_recommend_short(diet_skill: DietSkill):
    """'吃什么' 返回的 advice 不超过 60 字（中文字符）"""
    result = await diet_skill.recommend(
        time_of_day="午餐",
        preferences={},
        budget_level="medium",
        mood="neutral",
        location="",
    )
    # Count all non-whitespace characters
    char_count = len("".join(result.advice.split()))
    assert char_count <= 60, f"Advice too long ({char_count} chars): {result.advice!r}"


@pytest.mark.asyncio
async def test_food_mood_no_budget(diet_skill: DietSkill):
    """'想吃点好的' 返回的 advice 不包含'预算'、'搜索词'"""
    result = await diet_skill.recommend(
        time_of_day="晚餐",
        preferences={},
        budget_level="high",
        mood="sad",
        location="",
    )
    assert "预算" not in result.advice, f"Advice should not contain '预算': {result.advice!r}"
    assert "搜索词" not in result.advice, f"Advice should not contain '搜索词': {result.advice!r}"


@pytest.mark.asyncio
async def test_study_plan_max_3_steps(study_skill: StudySkill):
    """'明天考试但没复习' 返回的建议不超过 3 步"""
    result = await study_skill.plan_exam(
        days_left=1,
        subjects=["高数"],
        energy_level="low",
    )
    # Count numbered steps
    steps = [line for line in result.advice.split("\n")
             if line.strip() and line.strip()[0].isdigit()]
    assert len(steps) <= 3, f"Plan has {len(steps)} steps, expected <= 3: {result.advice!r}"


def test_detailed_plan_allows_full():
    """'给我详细计划一下' 返回 verbosity 应为 'card' 或 'full'"""
    fake_input = SkillInput(
        user_message="给我详细计划一下明天考试但没复习",
        intent=None,
        memory=None,
        user_state=None,
        recent_history=[],
    )
    result = study_plan_skill(fake_input)
    assert result.verbosity_level in ("card", "full"), (
        f"Expected verbosity 'card' or 'full', got {result.verbosity_level!r}"
    )


@pytest.mark.asyncio
async def test_social_reply_copyable(social_skill: SocialSkill):
    """'别人问我在干嘛怎么回' 返回可复制句子（至少 2 个选项）"""
    result = await social_skill.reply_advice(
        message_from_other="在干嘛",
        context="",
        relationship_stage="crush",
    )
    # Count numbered options
    options = [line for line in result.advice.split("\n")
               if line.strip().startswith(("1.", "2.", "3.", "4.", "5."))]
    assert len(options) >= 2, (
        f"Expected >= 2 copyable options, got {len(options)}: {result.advice!r}"
    )
