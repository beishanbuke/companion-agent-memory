"""
Skill Contracts - 技能输入输出协议

统一技能接口，让 life_skills.py 的技能返回结构化结果，
便于前端展示 user_visible_cards。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SkillInput:
    user_message: str
    intent: Any
    memory: Any
    user_state: Any
    recent_history: list[dict] = field(default_factory=list)


@dataclass
class SkillOutput:
    name: str
    should_show: bool
    summary_for_prompt: str
    user_visible_cards: list[dict] = field(default_factory=list)
    debug: dict = field(default_factory=dict)
