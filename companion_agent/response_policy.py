"""
Response Policy

Orchestrates the final response based on:
- Situation routing decision
- Memory context
- Skill execution results
- Safety checks

Responsible for:
- Formatting the response
- Adding safety disclaimers when needed
- Managing proactive behavior
- Enforcing response boundaries
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .situation_router import RoutingDecision
from .memory_adapter import TieredMemoryContext


@dataclass
class ResponseContext:
    """Context for response generation."""
    user_message: str
    situation: str
    memory_context: TieredMemoryContext
    skill_results: list[dict[str, Any]]
    conversation_history: list[dict[str, str]]
    safety_flag: bool


class ResponsePolicy:
    """Manages response formatting and safety checks."""

    # Safety levels for campus/China context
    SAFETY_LEVELS = {
        "low": "普通低落",
        "medium": "明显痛苦但无自伤意图",
        "high": "出现自伤/自杀/伤害他人表达",
    }

    # Safety disclaimers by level
    SAFETY_DISCLAIMERS = {
        "low": "",
        "medium": (
            "\n\n---"
            "\n如果你最近一直很难受，可以考虑和学校心理中心聊聊，"
            "或者找身边信任的人说说。"
        ),
        "high": (
            "\n\n---"
            "\n这句话我会认真对待。现在先别一个人扛着，"
            "尽快联系身边能马上找到你的人，比如室友、同学、家人或学校心理中心。"
            "如果你已经有伤害自己的计划，请立刻拨打当地紧急电话，"
            "或者让身边的人陪你去急诊/校医院。"
            "\n- 北京心理危机研究与干预中心：010-82951332"
            "\n- 全国24小时心理援助热线：400-161-9995"
            "\n- 紧急情况下请拨打 120 或 110"
        ),
    }

    # Crisis keywords for high-level detection
    CRISIS_KEYWORDS = [
        "想死", "自杀", "自残", "不想活", "活不下去",
        "杀", "伤害别人", "报复", "同归于尽",
        "suicide", "kill myself", "self-harm", "want to die",
    ]

    # Medium risk keywords
    MEDIUM_RISK_KEYWORDS = [
        "抑郁", "焦虑", "崩溃", "绝望", "很痛苦", "很难受",
        "睡不着", "吃不下", "无法集中", "什么都不想做",
        "depressed", "anxiety", "breaking down", "hopeless",
    ]

    # Response style modifiers
    STYLE_MODIFIERS = {
        "casual": "保持轻松自然的语气，像朋友聊天。",
        "empathetic": "先表达理解和共情，再提供支持。避免说教。",
        "structured": "逻辑清晰，分步骤说明。使用列表或编号。",
        "enthusiastic": "热情但不过度，分享你的兴奋。",
        "encouraging": "鼓励为主，肯定用户的努力。",
        "technical": "直接、准确、简洁。代码优先，解释其次。",
        "reminiscent": "温和地回忆，不要过度强调'我记得'。",
        "direct": "直奔主题，快速给出结果或行动方案。",
        "supportive": "冷静、支持、不评判。强调专业帮助的重要性。",
        "gentle": "温和、耐心、不催促。给用户空间。",
    }

    def __init__(self):
        self.proactive_enabled = True
        self.proactive_cooldown = 0  # Turns since last proactive message

    def build_prompt_suffix(
        self,
        routing: RoutingDecision,
        memory_context: TieredMemoryContext,
    ) -> str:
        """Build a prompt suffix based on routing and memory.

        This is appended to the system prompt to guide response style.
        """
        parts = []

        # Style modifier
        style = self.STYLE_MODIFIERS.get(routing.response_style, "")
        if style:
            parts.append(f"【回复风格】{style}")

        # Memory-aware guidance
        if routing.retrieve_memory and memory_context.memory_count > 0:
            parts.append(
                f"【记忆提示】当前已检索到 {memory_context.memory_count} 条相关记忆，"
                f"请在回复中自然地融入这些信息。"
            )

        # Skill guidance
        if routing.activate_skills:
            skill_names = ", ".join(routing.activate_skills)
            parts.append(f"【技能激活】已激活技能：{skill_names}")

        # Safety guidance
        if routing.safety_flag:
            parts.append(
                "【安全提醒】这是安全敏感场景。保持冷静、支持、不评判。"
                "如果涉及自伤/伤害他人风险，必须建议寻求专业帮助。"
            )

        return "\n".join(parts) if parts else ""

    def detect_safety_level(self, user_message: str) -> str:
        """Detect safety level from user message (low/medium/high)."""
        msg_lower = user_message.lower()

        # High: crisis keywords
        if any(kw in msg_lower for kw in self.CRISIS_KEYWORDS):
            return "high"

        # Medium: distress keywords
        if any(kw in msg_lower for kw in self.MEDIUM_RISK_KEYWORDS):
            return "medium"

        return "low"

    def format_response(
        self,
        raw_response: str,
        context: ResponseContext,
    ) -> str:
        """Format the final response.

        Adds safety disclaimers based on level, manages length, etc.
        """
        response = raw_response.strip()

        # Determine safety level from user message
        safety_level = self.detect_safety_level(context.user_message)

        # Add safety disclaimer only for medium/high risk
        if safety_level in ("medium", "high"):
            response = self._add_safety_disclaimer(response, safety_level)

        # Enforce length limit (soft)
        response = self._enforce_length(response, max_sentences=8)

        return response

    def _add_safety_disclaimer(self, response: str, level: str = "medium") -> str:
        """Add safety disclaimer appropriate to risk level if not already present."""
        disclaimer = self.SAFETY_DISCLAIMERS.get(level, "")
        if not disclaimer:
            return response
        # Avoid duplicating if already present
        if "心理中心" in response or "紧急电话" in response or "心理援助" in response:
            return response
        return response + disclaimer

    def _enforce_length(self, response: str, max_sentences: int = 8) -> str:
        """Soft length enforcement - only warns if too long."""
        # Count sentences (Chinese and English)
        import re
        sentences = re.split(r'[。！？.!?]+', response)
        sentences = [s.strip() for s in sentences if s.strip()]

        if len(sentences) > max_sentences:
            # Add a gentle note (for logging, not user-facing)
            # In production, you might want to summarize or truncate
            pass

        return response

    def should_be_proactive(self, turns_since_last: int) -> bool:
        """Decide if agent should be proactive.

        Proactive behavior is limited to avoid being intrusive.
        """
        if not self.proactive_enabled:
            return False

        # Cooldown: don't be proactive too frequently
        if turns_since_last < 5:
            return False

        return True

    def get_proactive_prompt(self, memory_context: TieredMemoryContext) -> str:
        """Generate a proactive prompt when agent initiates conversation."""
        # Only proactive about goals and routines, not intrusive questions
        goals = memory_context.long_term_goals
        if goals:
            goal = goals[0]
            return (
                f"用户之前提到过目标：{goal.get('description', '')}。"
                f"可以温和地问问进展，但不要太pushy。"
            )

        return "可以自然地打个招呼，或者分享一个轻松的话题。"
