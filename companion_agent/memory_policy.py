"""
Memory Update Policy

Decides whether each user message should be stored, updated, deleted, or ignored.
Uses a lightweight LLM call or rule-based system to evaluate memory worthiness.

Policy questions:
1. Is this message worth remembering?
2. Add, update, delete, or ignore?
3. Does it involve privacy/sensitive info?
4. Should we ask user for confirmation?
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

import openai


@dataclass
class MemoryDecision:
    """Decision about whether to update memory."""
    action: str  # "add", "update", "delete", "ignore"
    reason: str
    confidence: float  # 0.0 - 1.0
    requires_confirmation: bool
    privacy_level: str  # "public", "private", "sensitive"
    suggested_tags: list[str]


class MemoryUpdatePolicy:
    """Evaluates whether to store/update/delete memories."""

    # Patterns that suggest explicit memory commands
    DELETE_PATTERNS = [
        "忘掉", "删除", "去掉", "清除", "别再记", "忘记",
        "forget", "delete", "remove", "clear", "stop remembering",
    ]

    UPDATE_PATTERNS = [
        "改成", "改为", "更新了", "变了", "现在是",
        "changed to", "updated to", "now is", "switched to",
    ]

    # Patterns that should NEVER be stored (short, greeting, low-info)
    NEVER_STORE_PATTERNS = [
        "你好", "在吗", "哈喽", "谢谢", "好的", "嗯嗯", "哈哈",
        "我累了", "好烦", "无语", "困了", "早安", "晚安", "再见",
        "how are you", "what's up", "good morning", "good night",
        "hi", "hello", "hey", "ok", "okay", "thanks", "bye",
    ]

    # Sensitive mental health / personal struggle patterns that need confirmation
    SENSITIVE_MENTAL_PATTERNS = [
        "睡不着", "抑郁", "焦虑", "崩溃", "想死", "自杀", "自残",
        "不想活", "活不下去", "很难受", "很痛苦", "绝望",
        "家里关系差", "和父母吵架", "失恋", "被孤立",
    ]

    # Sensitive patterns that need confirmation
    SENSITIVE_PATTERNS = [
        "密码", "账号", "身份证", "银行卡", "地址", "电话",
        "password", "account", "credit card", "address", "phone",
        "病", "药", "医院", "医生", "诊断",
        "sick", "medicine", "hospital", "doctor", "diagnosis",
    ]

    def __init__(self, model: str = "gpt-4o-mini"):
        self.model = model
        self._client = None
        self._init_client()

    def _init_client(self) -> None:
        """Initialize OpenAI client from environment."""
        api_key = os.getenv("OPENAI_API_KEY", "")
        base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        if api_key:
            self._client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url)

    async def evaluate(
        self,
        user_message: str,
        current_memory_snapshot: dict[str, Any],
        situation: str = "casual_chat",
        use_llm: bool = False,
    ) -> MemoryDecision:
        """Evaluate whether to update memory.

        Uses fast rule-based evaluation by default. LLM is disabled for speed.
        Set use_llm=True if you need nuanced decisions.
        """
        # Fast path: never store short greetings / low-info messages
        if self._should_never_store(user_message):
            return MemoryDecision(
                action="ignore",
                reason="短句/寒暄/低信息密度内容，不写入长期记忆",
                confidence=0.95,
                requires_confirmation=False,
                privacy_level="public",
                suggested_tags=[],
            )

        # Fast path: explicit delete commands
        if self._is_explicit_delete(user_message):
            return MemoryDecision(
                action="delete",
                reason="用户明确要求删除记忆",
                confidence=0.9,
                requires_confirmation=True,
                privacy_level="private",
                suggested_tags=["user_request", "delete"],
            )

        # Fast path: low-value messages
        if self._is_low_value(user_message):
            return MemoryDecision(
                action="ignore",
                reason="低价值信息，不值得记忆",
                confidence=0.8,
                requires_confirmation=False,
                privacy_level="public",
                suggested_tags=[],
            )

        # Check sensitive mental health / personal struggle patterns
        is_sensitive_mental = self._check_sensitive_mental(user_message)

        # Fast path: sensitive info
        is_sensitive, privacy_level = self._check_sensitive(user_message)

        # Sensitive mental health content requires confirmation before storing
        if is_sensitive_mental:
            return MemoryDecision(
                action="pending",
                reason="涉及个人心理状态/困境，需用户确认后再存入长期记忆",
                confidence=0.85,
                requires_confirmation=True,
                privacy_level="sensitive",
                suggested_tags=["mental_health", "sensitive"],
            )

        # LLM fallback only if explicitly enabled
        if use_llm and self._client and len(user_message) > 10:
            return await self._llm_evaluate(user_message, current_memory_snapshot, situation, privacy_level)

        # Rule-based fallback (fast, no extra LLM call)
        return self._rule_based_evaluate(user_message, privacy_level)

    def _is_explicit_delete(self, message: str) -> bool:
        """Check if user is asking to delete memory."""
        msg_lower = message.lower()
        return any(pattern in msg_lower for pattern in self.DELETE_PATTERNS)

    def _should_never_store(self, message: str) -> bool:
        """Check if message should never be stored (short greetings, trivial)."""
        s = message.strip()
        # Very short messages (<=6 chars)
        if len(s) <= 6:
            return True
        # Exact match against never-store patterns
        if s in self.NEVER_STORE_PATTERNS:
            return True
        # One-off emotional venting (very short + emotional words)
        if len(s) <= 12:
            venting_markers = ["累了", "烦", "困", "无语", "崩溃", "emo"]
            if any(m in s for m in venting_markers):
                return True
        return False

    def _check_sensitive_mental(self, message: str) -> bool:
        """Check if message contains sensitive mental health / personal struggle content."""
        msg_lower = message.lower()
        return any(pattern in msg_lower for pattern in self.SENSITIVE_MENTAL_PATTERNS)

    def _is_low_value(self, message: str) -> bool:
        """Check if message is low-value trivia (but not as strict as never-store)."""
        # Already handled by _should_never_store for very short messages
        if len(message) < 15:
            return False  # Let _should_never_store handle these

        msg_lower = message.lower()

        # Weather, routine small talk
        routine_markers = ["今天天气", "吃了", "喝了", "走了", "来了", "看了", "听了"]
        if any(pattern in msg_lower for pattern in routine_markers):
            # But allow if it contains preference indicators
            preference_markers = ["喜欢", "讨厌", "不爱", "prefer", "like", "dislike", "hate"]
            if not any(m in msg_lower for m in preference_markers):
                return True

        return False

    def _check_sensitive(self, message: str) -> tuple[bool, str]:
        """Check if message contains sensitive info."""
        msg_lower = message.lower()
        sensitive_count = sum(1 for p in self.SENSITIVE_PATTERNS if p in msg_lower)

        if sensitive_count >= 2:
            return True, "sensitive"
        elif sensitive_count == 1:
            return True, "private"
        return False, "public"

    def _rule_based_evaluate(self, message: str, privacy_level: str) -> MemoryDecision:
        """Simple rule-based evaluation."""
        msg_lower = message.lower()

        # Check for preference statements
        preference_indicators = [
            "喜欢", "爱", "讨厌", "不喜欢", "偏好", "习惯",
            "prefer", "like", "love", "hate", "dislike", "favorite",
            "总是", "经常", "从不", "usually", "always", "never",
        ]

        has_preference = any(ind in msg_lower for ind in preference_indicators)

        # Check for factual statements about self
        self_indicators = [
            "我是", "我在", "我有", "我叫", "我住", "我的工作",
            "i am", "i'm", "i live", "i work", "my name", "my job",
        ]
        has_self_fact = any(ind in msg_lower for ind in self_indicators)

        # Check for goal/intention
        goal_indicators = [
            "想", "打算", "计划", "目标", "希望", "要",
            "want to", "plan to", "goal", "aim to", "hope to",
        ]
        has_goal = any(ind in msg_lower for ind in goal_indicators)

        if has_preference or has_self_fact or has_goal:
            return MemoryDecision(
                action="add",
                reason="包含用户偏好、事实或目标",
                confidence=0.75,
                requires_confirmation=privacy_level == "sensitive",
                privacy_level=privacy_level,
                suggested_tags=["preference" if has_preference else "", "profile" if has_self_fact else "", "goal" if has_goal else ""],
            )

        return MemoryDecision(
            action="ignore",
            reason="未检测到值得记忆的信息",
            confidence=0.6,
            requires_confirmation=False,
            privacy_level=privacy_level,
            suggested_tags=[],
        )

    async def _llm_evaluate(
        self,
        message: str,
        snapshot: dict[str, Any],
        situation: str,
        privacy_level: str,
    ) -> MemoryDecision:
        """Use LLM for nuanced memory evaluation."""
        # Build context about existing memories
        existing_keys = list(snapshot.get("persona_slots", {}).keys())[:10]
        existing_prefs = list(snapshot.get("preference_slots", {}).keys())[:10]

        prompt = f"""你是一个记忆管理助手。请判断用户的这句话是否值得存入长期记忆。

现有记忆键：
- 档案：{', '.join(existing_keys) or '无'}
- 偏好：{', '.join(existing_prefs) or '无'}

用户消息：{message!r}

请输出 JSON：
{{
  "action": "add/update/delete/ignore",
  "reason": "简要说明",
  "confidence": 0.0-1.0,
  "requires_confirmation": true/false,
  "privacy_level": "public/private/sensitive",
  "suggested_tags": ["tag1", "tag2"]
}}

规则：
- 偏好、习惯、目标、重要事实 → add
- 修改已有信息 → update
- 明确要求忘记 → delete
- 日常琐事、一次性信息 → ignore
- 敏感信息（健康、财务、身份）→ requires_confirmation=true"""

        try:
            response = await self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "你是一个记忆管理助手，只输出 JSON。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                max_tokens=200,
            )
            content = response.choices[0].message.content or ""
            # Extract JSON
            json_start = content.find("{")
            json_end = content.rfind("}")
            if json_start >= 0 and json_end > json_start:
                data = json.loads(content[json_start:json_end + 1])
                return MemoryDecision(
                    action=data.get("action", "ignore"),
                    reason=data.get("reason", ""),
                    confidence=float(data.get("confidence", 0.5)),
                    requires_confirmation=bool(data.get("requires_confirmation", False)),
                    privacy_level=data.get("privacy_level", privacy_level),
                    suggested_tags=data.get("suggested_tags", []),
                )
        except Exception:
            pass  # Fall back to rule-based

        return self._rule_based_evaluate(message, privacy_level)

    def should_store(self, decision: MemoryDecision) -> bool:
        """Quick check if decision says to store."""
        return decision.action in ("add", "update")

    def should_confirm(self, decision: MemoryDecision) -> bool:
        """Check if user confirmation is needed."""
        return decision.requires_confirmation or decision.privacy_level == "sensitive"
