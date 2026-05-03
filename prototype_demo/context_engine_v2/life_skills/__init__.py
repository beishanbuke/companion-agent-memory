"""本科生生活能力包

不是硬规则，是 LLM 驱动的能力层。
每个 advisor 负责一个生活领域，用自然语言理解 + 结构化输出。

设计原则：
1. 理解优先：先理解用户具体情况，再给建议
2. 微行动：不给大计划，给"现在能做的一件小事"
3. 个性化：结合用户记忆（如果有）
4. 允许不知道：没有数据时诚实说，不编造
"""

from __future__ import annotations

from .diet_advisor import DietAdvisor, DietAdvice
from .study_coach import StudyCoach, StudyPlan
from .social_advisor import SocialAdvisor, SocialAdvice

__all__ = [
    "DietAdvisor",
    "DietAdvice",
    "StudyCoach",
    "StudyPlan",
    "SocialAdvisor",
    "SocialAdvice",
]
