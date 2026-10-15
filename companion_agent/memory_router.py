"""
Memory Router

Separates memory routing from situation routing.

The router decides:
- whether memory should be used at all
- which memory tiers should be retrieved
- whether the final response may explicitly mention old memory

This module is intentionally structured around versioned strategies so future
router variants can be added without rewriting the integration points.
"""

from __future__ import annotations

import re
import json
import os
from urllib import request
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class MemoryRouteDecision:
    """Decision for long-term memory retrieval and usage."""

    need_memory: bool
    retrieval_mode: str = "none"  # none | background | explicit
    tiers: list[str] = field(default_factory=list)
    max_items: int = 0
    max_per_tier: dict[str, int] = field(default_factory=dict)
    mention_policy: str = "forbid"  # forbid | implicit_only | explicit_ok
    reason: str = ""
    strategy_version: str = "rule_based_v1"
    confidence: float = 0.0
    signals: list[str] = field(default_factory=list)
    tier_scores: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.need_memory:
            self.retrieval_mode = "none"
            self.tiers = []
            self.max_items = 0
            self.max_per_tier = {}
            self.mention_policy = "forbid"
        else:
            self.tiers = _dedupe_preserve_order(self.tiers)
            if not self.max_items:
                self.max_items = sum(self.max_per_tier.values()) or max(len(self.tiers), 1)
            if self.mention_policy not in {"forbid", "implicit_only", "explicit_ok"}:
                self.mention_policy = "implicit_only"


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    output: list[str] = []
    for value in values:
        normalized = str(value).strip()
        if normalized and normalized not in output:
            output.append(normalized)
    return output


class MemoryRouterStrategy(Protocol):
    version: str

    def route(
        self,
        *,
        user_message: str,
        conversation_history: list[dict[str, str]] | None = None,
        situation: str = "casual_chat",
        situation_confidence: float = 0.0,
        current_memory_snapshot: dict[str, Any] | None = None,
    ) -> MemoryRouteDecision:
        ...


class RuleBasedMemoryRouterV1:
    """First rule-based memory router.

    Goals:
    - suppress memory use for generic or transform-like tasks
    - allow background memory for personalized support/advice
    - allow explicit memory mention only for genuine recall requests
    """

    version = "rule_based_v1"

    EXPLICIT_DISABLE_PATTERNS = [
        "别参考我以前",
        "先不结合我过去",
        "不用记得我是谁",
        "不要结合我过去",
        "不要参考我以前",
        "按普通用户回答",
        "不要用我以前的",
        "别管我之前",
        "不要结合之前的记忆",
        "just answer normally",
        "don't use my past",
        "don't use previous memory",
    ]

    SHORT_TERM_PATTERNS = [
        "我刚才说了啥",
        "我刚刚说了啥",
        "我刚才说了什么",
        "我刚刚说了什么",
        "今天这段代码报什么错",
        "what did i just say",
        "what error did this code show today",
    ]

    EXPLICIT_RECALL_PATTERNS = [
        r"^你还记得",
        r"^你记得",
        r"^我之前说过",
        r"^我平时喜欢",
        r"^我是不是以前说过",
        r"^我上次.*你.*记得",
        r"^你还有印象吗",
        r"^do you remember",
        r"^what do you remember",
        r"^what is my name",
        r"^where do i live",
    ]

    GENERIC_TASK_PATTERNS = [
        "翻成",
        "翻译",
        "改写",
        "润色",
        "总结",
        "列成",
        "bullet",
        "points",
        "改成更",
        "解释一下",
        "什么意思",
        "是什么",
        "区别",
        "帮我列一个通用的",
        "通用",
        "大众推荐",
        "普通用户",
        "按照普通",
    ]

    CODE_OR_KNOWLEDGE_KEYWORDS = [
        "python",
        "javascript",
        "docker",
        "http",
        "git",
        "regex",
        "api",
        "append",
        "extend",
        "过拟合",
        "华氏度",
        "摄氏度",
        "星期几",
        "mp3",
        "wav",
        "rebase",
        "404",
        "500",
    ]

    PERSONAL_STATE_KEYWORDS = [
        "我今天",
        "我最近",
        "我现在",
        "有点累",
        "有点烦",
        "有点困",
        "脑雾",
        "提不起劲",
        "不太想动",
        "不想太累",
        "孤单",
        "紧张",
        "压力",
        "不想太甜",
        "不想太辣",
        "不想太吵",
        "不想和很多人待在一起",
        "不想热闹",
        "不想说空话",
        "怎么跟我说话",
    ]

    ADVICE_KEYWORDS = [
        "适合",
        "合适",
        "比较好",
        "建议",
        "怎么做",
        "做什么",
        "选什么",
        "喝的",
        "吃什么",
        "吃点什么",
        "怎么安排",
        "怎么恢复",
        "怎么安慰",
        "第一步",
        "先改哪",
        "先做哪种",
        "该买点什么",
    ]

    PREFERENCE_CUES = {
        "preferences": [
            "喝",
            "饮料",
            "饮品",
            "吃",
            "口味",
            "甜",
            "辣",
            "音乐",
            "歌",
            "运动",
            "散步",
            "羽毛球",
            "篮球",
            "安慰",
            "怎么跟我说话",
            "局",
            "热闹",
        ],
        "episodic_events": [
            "最近",
            "上周",
            "上次",
            "这周",
            "今天",
            "前阵子",
            "为什么最近",
            "为什么总",
            "最近在忙什么",
        ],
        "long_term_goals": [
            "长期目标",
            "目标",
            "改进",
            "作息",
            "效率",
            "复习",
            "长期",
            "第一步",
        ],
        "profile": [
            "我叫什么",
            "我住哪",
            "我住哪里",
            "我是什么身份",
            "我现在住在哪",
            "住在哪一带",
            "住在哪里",
            "做什么",
            "职业",
            "工作",
            "身份",
        ],
    }

    DEFAULT_LIMITS = {
        "profile": 1,
        "preferences": 2,
        "long_term_goals": 1,
        "episodic_events": 2,
        "safety_notes": 2,
    }

    def route(
        self,
        *,
        user_message: str,
        conversation_history: list[dict[str, str]] | None = None,
        situation: str = "casual_chat",
        situation_confidence: float = 0.0,
        current_memory_snapshot: dict[str, Any] | None = None,
    ) -> MemoryRouteDecision:
        del conversation_history, situation_confidence, current_memory_snapshot

        message = (user_message or "").strip()
        lowered = message.lower()

        if self._matches_any(lowered, self.EXPLICIT_DISABLE_PATTERNS):
            return MemoryRouteDecision(
                need_memory=False,
                reason="user_explicitly_disabled_memory",
                strategy_version=self.version,
            )

        if self._matches_any(lowered, self.SHORT_TERM_PATTERNS):
            return MemoryRouteDecision(
                need_memory=False,
                reason="short_term_context_request",
                strategy_version=self.version,
            )

        if self._is_explicit_recall(message, lowered):
            tiers = self._infer_explicit_tiers(message, lowered)
            return MemoryRouteDecision(
                need_memory=True,
                retrieval_mode="explicit",
                tiers=tiers,
                max_per_tier=self._limits_for(tiers),
                mention_policy="explicit_ok",
                reason="explicit_memory_recall",
                strategy_version=self.version,
            )

        if self._is_generic_no_memory_task(message, lowered, situation):
            return MemoryRouteDecision(
                need_memory=False,
                reason="generic_or_transform_task",
                strategy_version=self.version,
            )

        if self._should_use_background_memory(message, lowered, situation):
            tiers = self._infer_background_tiers(message, lowered, situation)
            return MemoryRouteDecision(
                need_memory=True,
                retrieval_mode="background",
                tiers=tiers,
                max_per_tier=self._limits_for(tiers),
                mention_policy="implicit_only",
                reason="personalized_background_memory",
                strategy_version=self.version,
            )

        return MemoryRouteDecision(
            need_memory=False,
            reason="default_no_memory",
            strategy_version=self.version,
        )

    def _matches_any(self, text: str, patterns: list[str]) -> bool:
        return any(pattern in text for pattern in patterns)

    def _is_explicit_recall(self, message: str, lowered: str) -> bool:
        if any(re.search(pattern, lowered) for pattern in self.EXPLICIT_RECALL_PATTERNS):
            return True
        return "记得" in message and any(
            cue in message
            for cue in ["喜欢", "叫什么", "住哪", "住哪里", "上周", "上次", "目标", "最近", "忙什么"]
        )

    def _is_generic_no_memory_task(self, message: str, lowered: str, situation: str) -> bool:
        if self._matches_any(lowered, self.GENERIC_TASK_PATTERNS):
            return True

        if any(keyword in lowered for keyword in self.CODE_OR_KNOWLEDGE_KEYWORDS):
            return True

        if situation in {"coding_helper", "tool_task"}:
            return True

        if situation == "learning_coach" and not self._has_personalization_signal(message, lowered):
            return True

        if self._looks_like_generic_question(message, lowered) and not self._has_personalization_signal(message, lowered):
            return True

        return False

    def _looks_like_generic_question(self, message: str, lowered: str) -> bool:
        if any(token in lowered for token in ["是什么", "什么意思", "区别", "how", "what is", "difference"]):
            return True
        if re.search(r"\b\d+(\.\d+)?\b", message) and any(
            token in lowered for token in ["多少", "几", "等于", "多久", "星期"]
        ):
            return True
        return False

    def _has_personalization_signal(self, message: str, lowered: str) -> bool:
        if any(keyword in message for keyword in self.PERSONAL_STATE_KEYWORDS):
            return True
        if any(keyword in message for keyword in self.ADVICE_KEYWORDS) and "我" in message:
            return True
        if "按照我之前的习惯" in message:
            return True
        if "适合我" in message or "跟我说话" in message:
            return True
        if situation_like_food_or_music(lowered) and "我" in message:
            return True
        return False

    def _should_use_background_memory(self, message: str, lowered: str, situation: str) -> bool:
        if situation in {"emotional_support", "planning", "personal_routine", "safety_sensitive"}:
            return True

        if self._has_personalization_signal(message, lowered):
            return True

        if situation == "casual_chat" and ("我" in message) and any(
            cue in message for cue in ["想", "有点", "今天", "最近", "周末", "今晚", "明天"]
        ):
            return True

        return False

    def _infer_explicit_tiers(self, message: str, lowered: str) -> list[str]:
        tiers = []
        if any(cue in message for cue in self.PREFERENCE_CUES["profile"]):
            tiers.append("profile")
        if any(cue in message for cue in self.PREFERENCE_CUES["long_term_goals"]):
            tiers.append("long_term_goals")
        if any(cue in message for cue in self.PREFERENCE_CUES["episodic_events"]):
            tiers.append("episodic_events")
        if any(cue in message for cue in self.PREFERENCE_CUES["preferences"]) or "喜欢" in message:
            tiers.append("preferences")

        if not tiers:
            if "记得" in message or "以前" in message:
                tiers.append("episodic_events")

        return _dedupe_preserve_order(tiers)

    def _infer_background_tiers(self, message: str, lowered: str, situation: str) -> list[str]:
        tiers: list[str] = []

        if situation == "safety_sensitive":
            tiers.extend(["safety_notes", "profile"])

        if any(cue in message for cue in self.PREFERENCE_CUES["preferences"]):
            tiers.append("preferences")

        if any(cue in message for cue in self.PREFERENCE_CUES["episodic_events"]) or situation == "emotional_support":
            tiers.append("episodic_events")

        if any(cue in message for cue in self.PREFERENCE_CUES["long_term_goals"]) or situation == "planning":
            tiers.append("long_term_goals")

        if any(cue in message for cue in self.PREFERENCE_CUES["profile"]):
            tiers.append("profile")

        if situation == "personal_routine" and "preferences" not in tiers:
            tiers.append("preferences")

        if not tiers and situation == "casual_chat":
            tiers.append("preferences")

        return _dedupe_preserve_order(tiers)

    def _limits_for(self, tiers: list[str]) -> dict[str, int]:
        return {tier: self.DEFAULT_LIMITS.get(tier, 1) for tier in tiers}


class RuleBasedMemoryRouterV2(RuleBasedMemoryRouterV1):
    """Signal-based router with independent intent and tier selection.

    Situation classification is treated as a weak hint. Explicit user intent
    and personalization signals always take precedence, and unavailable tiers
    are removed when a memory snapshot is supplied.
    """

    version = "rule_based_v2"
    TIER_THRESHOLD = 0.45
    MAX_TIERS = 2
    DEFAULT_LIMITS = {
        "profile": 5,
        "preferences": 2,
        "long_term_goals": 1,
        "episodic_events": 2,
        "safety_notes": 2,
    }
    GOAL_TAGS = {
        "goal", "objective", "plan", "target", "aim", "resolution",
        "目标", "计划", "打算", "决心", "愿望",
    }
    SAFETY_TAGS = {
        "safety", "crisis", "emergency", "health", "mental_health",
        "depression", "suicide", "self_harm", "violence", "abuse",
        "敏感", "安全", "危机", "健康", "心理", "抑郁", "自残", "暴力",
    }

    GENERIC_AUDIENCE_CUES = [
        "适合新手", "给新手", "通用", "大众", "普通用户", "一般来说",
        "for beginners", "generic", "in general",
    ]
    THIRD_PARTY_CUES = [
        "我妈", "我爸", "我朋友", "我同学", "我对象", "他喜欢", "她喜欢",
        "一个喜欢", "someone who", "my friend", "my mother", "my father",
    ]
    HISTORY_FOLLOWUP_CUES = ["那这个呢", "那我呢", "为什么", "然后呢", "还是这样吗", "what about me"]

    def _is_explicit_recall(self, message: str, lowered: str) -> bool:
        if super()._is_explicit_recall(message, lowered):
            return True
        return bool(
            re.search(r"^我之前提过.*(?:吗|么)[？?]?$", message)
            or re.search(r"(?:上次|以前|之前).*(?:有印象|记得)(?:吗|么)?[？?]?$", message)
        )

    def route(
        self,
        *,
        user_message: str,
        conversation_history: list[dict[str, str]] | None = None,
        situation: str = "casual_chat",
        situation_confidence: float = 0.0,
        current_memory_snapshot: dict[str, Any] | None = None,
    ) -> MemoryRouteDecision:
        message = (user_message or "").strip()
        lowered = message.lower()
        history = conversation_history or []
        snapshot_supplied = current_memory_snapshot is not None
        available_tiers = self._available_tiers(current_memory_snapshot or {})

        if self._matches_any(lowered, self.EXPLICIT_DISABLE_PATTERNS):
            return self._no_memory("user_explicitly_disabled_memory", 1.0, ["explicit_disable"])

        if self._matches_any(lowered, self.SHORT_TERM_PATTERNS):
            return self._no_memory("short_term_context_request", 1.0, ["short_term_context"])

        if self._is_third_party_or_generic_audience(lowered):
            return self._no_memory("non_user_or_generic_audience", 0.95, ["generic_audience"])

        if self._is_explicit_recall(message, lowered):
            scores, signals = self._score_explicit_tiers(message, lowered)
            tiers = self._select_tiers(scores, available_tiers, snapshot_supplied)
            # An explicit query remains a memory query even when the store is empty;
            # the response should then state that no matching memory is available.
            return self._memory_decision(
                retrieval_mode="explicit",
                tiers=tiers,
                mention_policy="explicit_ok",
                reason="explicit_memory_recall",
                confidence=0.98,
                signals=["explicit_recall", *signals],
                tier_scores=scores,
            )

        personalized, personal_signals = self._personalization_signals(message, lowered, history)
        if self._is_generic_no_memory_task_v2(message, lowered, situation, personalized):
            return self._no_memory("generic_or_transform_task", 0.9, ["generic_task"])

        should_use = personalized or situation in {
            "emotional_support", "planning", "personal_routine", "safety_sensitive"
        }
        if not should_use:
            return self._no_memory("default_no_memory", 0.75, ["no_personalization_signal"])

        scores, tier_signals = self._score_background_tiers(message, lowered, situation)
        if "preference_topic" in tier_signals and "personal_advice" in personal_signals:
            scores["episodic_events"] = 0.0
        tiers = self._select_tiers(scores, available_tiers, snapshot_supplied)
        if snapshot_supplied and not tiers:
            return self._no_memory(
                "no_relevant_memory_available", 0.85, [*personal_signals, "empty_relevant_tiers"]
            )

        return self._memory_decision(
            retrieval_mode="background",
            tiers=tiers,
            mention_policy="implicit_only",
            reason="personalized_background_memory",
            confidence=min(0.95, 0.65 + 0.08 * len(personal_signals)),
            signals=[*personal_signals, *tier_signals],
            tier_scores=scores,
        )

    def _no_memory(self, reason: str, confidence: float, signals: list[str]) -> MemoryRouteDecision:
        return MemoryRouteDecision(
            need_memory=False,
            reason=reason,
            strategy_version=self.version,
            confidence=confidence,
            signals=_dedupe_preserve_order(signals),
        )

    def _memory_decision(
        self,
        *,
        retrieval_mode: str,
        tiers: list[str],
        mention_policy: str,
        reason: str,
        confidence: float,
        signals: list[str],
        tier_scores: dict[str, float],
    ) -> MemoryRouteDecision:
        max_per_tier = self._limits_for(tiers)
        max_items = sum(max_per_tier.values()) if retrieval_mode == "explicit" else 3
        return MemoryRouteDecision(
            need_memory=True,
            retrieval_mode=retrieval_mode,
            tiers=tiers,
            max_items=max_items,
            max_per_tier=max_per_tier,
            mention_policy=mention_policy,
            reason=reason,
            strategy_version=self.version,
            confidence=confidence,
            signals=_dedupe_preserve_order(signals),
            tier_scores={key: round(value, 3) for key, value in tier_scores.items()},
        )

    def _is_third_party_or_generic_audience(self, lowered: str) -> bool:
        return self._matches_any(lowered, self.GENERIC_AUDIENCE_CUES + self.THIRD_PARTY_CUES)

    def _is_generic_no_memory_task_v2(
        self, message: str, lowered: str, situation: str, personalized: bool
    ) -> bool:
        if self._matches_any(lowered, self.GENERIC_TASK_PATTERNS):
            return True
        if any(keyword in lowered for keyword in self.CODE_OR_KNOWLEDGE_KEYWORDS) and not personalized:
            return True
        if situation in {"coding_helper", "tool_task", "learning_coach"} and not personalized:
            return True
        return self._looks_like_generic_question(message, lowered) and not personalized

    def _personalization_signals(
        self, message: str, lowered: str, history: list[dict[str, str]]
    ) -> tuple[bool, list[str]]:
        signals: list[str] = []
        if any(keyword in message for keyword in self.PERSONAL_STATE_KEYWORDS):
            signals.append("personal_state")
        if any(keyword in message for keyword in self.ADVICE_KEYWORDS) and "我" in message:
            signals.append("personal_advice")
        if any(cue in message for cue in ["按照我之前", "按我之前", "适合我", "根据我的", "跟我说话"]):
            signals.append("explicit_personalization")
        if situation_like_food_or_music(lowered) and "我" in message:
            signals.append("personal_topic")
        if situation_like_personal_state(lowered) and "我" in message:
            signals.append("personal_state")
        if "我" in message and any(cue in message for cue in [
            "我想", "有点想", "给自己", "不想太", "不要太吵", "安静一下", "小奖励", "陪着我",
        ]):
            signals.append("personal_preference_request")
        if history and self._matches_any(lowered, self.HISTORY_FOLLOWUP_CUES):
            recent_text = " ".join(str(item.get("content", "")) for item in history[-4:]).lower()
            if any(cue in recent_text for cue in ["记得", "以前", "偏好", "喜欢", "习惯", "目标"]):
                signals.append("memory_followup")
        return bool(signals), _dedupe_preserve_order(signals)

    def _score_explicit_tiers(self, message: str, lowered: str) -> tuple[dict[str, float], list[str]]:
        scores = self._empty_scores()
        signals: list[str] = []
        for tier, cues in self.PREFERENCE_CUES.items():
            if any(cue in message for cue in cues):
                scores[tier] += 1.0
                signals.append(f"{tier}_cue")
        if "喜欢" in message:
            scores["preferences"] += 1.0
        if not any(scores.values()):
            scores["episodic_events"] = 0.8
            signals.append("generic_past_recall")
        return scores, signals

    def _score_background_tiers(
        self, message: str, lowered: str, situation: str
    ) -> tuple[dict[str, float], list[str]]:
        scores = self._empty_scores()
        signals: list[str] = []

        if any(cue in message for cue in self.PREFERENCE_CUES["preferences"]):
            scores["preferences"] += 0.9
            signals.append("preference_topic")
        if any(cue in message for cue in [
            "放松", "奖励", "太吵", "安静", "陪着", "出去", "透气", "容易坚持", "懒得",
        ]):
            scores["preferences"] += 0.65
            signals.append("preference_style")
        if any(cue in message for cue in self.PREFERENCE_CUES["episodic_events"]):
            scores["episodic_events"] += 0.8
            signals.append("temporal_state")
        if any(cue in message for cue in self.PREFERENCE_CUES["long_term_goals"]):
            scores["long_term_goals"] += 0.8
            signals.append("goal_topic")
        if any(cue in message for cue in self.PREFERENCE_CUES["profile"]):
            scores["profile"] += 1.0
            signals.append("profile_topic")

        if situation == "emotional_support" or situation_like_personal_state(lowered):
            scores["episodic_events"] += 0.55
            scores["preferences"] += 0.45
            signals.append("support_context")
        if any(cue in message for cue in ["懒得", "提不起劲", "没动力"]):
            scores["episodic_events"] += 0.55
            signals.append("low_energy_pattern")
        if situation == "planning":
            scores["long_term_goals"] += 0.45
        if situation == "personal_routine":
            scores["preferences"] += 0.45
        if situation == "safety_sensitive":
            scores["safety_notes"] += 1.0
            scores["profile"] += 0.45
            signals.append("safety_context")
        if any(cue in message for cue in ["危险的念头", "伤害自己", "自残", "不想活", "轻生", "撑不住"]):
            scores["safety_notes"] += 1.0
            scores["episodic_events"] = 0.0
            scores["preferences"] = 0.0
            signals.append("safety_keyword")
        if any(cue in message for cue in ["上课", "学校", "工作", "家里", "住"]):
            scores["profile"] += 0.5
            signals.append("profile_context")

        if not any(value >= self.TIER_THRESHOLD for value in scores.values()):
            scores["preferences"] = self.TIER_THRESHOLD
            signals.append("personalization_fallback")
        return scores, signals

    def _empty_scores(self) -> dict[str, float]:
        return {tier: 0.0 for tier in self.DEFAULT_LIMITS}

    def _select_tiers(
        self, scores: dict[str, float], available_tiers: set[str], snapshot_supplied: bool
    ) -> list[str]:
        ranked = sorted(scores, key=lambda tier: (-scores[tier], list(scores).index(tier)))
        selected = [tier for tier in ranked if scores[tier] >= self.TIER_THRESHOLD]
        if snapshot_supplied:
            selected = [tier for tier in selected if tier in available_tiers]
        return selected[: self.MAX_TIERS]

    def _available_tiers(self, snapshot: dict[str, Any]) -> set[str]:
        aliases = {
            "profile": ("profile", "persona_slots"),
            "preferences": ("preferences", "preference_slots", "preference_profiles"),
            "long_term_goals": ("long_term_goals",),
            "episodic_events": ("episodic_events",),
            "safety_notes": ("safety_notes",),
        }
        available = {
            tier for tier, keys in aliases.items() if any(bool(snapshot.get(key)) for key in keys)
        }
        for memory in snapshot.get("memories", []) or []:
            tags = set(memory.get("tags", []) or []) if isinstance(memory, dict) else set()
            if tags & self.GOAL_TAGS:
                available.add("long_term_goals")
            if tags & self.SAFETY_TAGS:
                available.add("safety_notes")
            if isinstance(memory, dict) and memory.get("memory_type") == "event":
                available.add("episodic_events")
        return available


class LLMJudgeMemoryRouterV1:
    """LLM-judged memory router with rule-based fallback."""

    version = "llm_judge_v1"
    ALLOWED_TIERS = {"profile", "preferences", "long_term_goals", "episodic_events", "safety_notes"}
    ALLOWED_MODES = {"none", "background", "explicit"}
    ALLOWED_MENTION_POLICIES = {"forbid", "implicit_only", "explicit_ok"}

    def __init__(self, fallback: RuleBasedMemoryRouterV2 | None = None):
        self.fallback = fallback or RuleBasedMemoryRouterV2()

    def route(
        self,
        *,
        user_message: str,
        conversation_history: list[dict[str, str]] | None = None,
        situation: str = "casual_chat",
        situation_confidence: float = 0.0,
        current_memory_snapshot: dict[str, Any] | None = None,
    ) -> MemoryRouteDecision:
        fallback_decision = self.fallback.route(
            user_message=user_message,
            conversation_history=conversation_history,
            situation=situation,
            situation_confidence=situation_confidence,
            current_memory_snapshot=current_memory_snapshot,
        )
        try:
            judged = self._judge(
                user_message=user_message,
                conversation_history=conversation_history or [],
                situation=situation,
                situation_confidence=situation_confidence,
                current_memory_snapshot=current_memory_snapshot or {},
            )
            return self._decision_from_judge(judged, current_memory_snapshot, fallback_decision)
        except Exception as exc:
            fallback_decision.strategy_version = f"{self.version}_fallback"
            fallback_decision.signals = _dedupe_preserve_order([
                *fallback_decision.signals,
                "llm_judge_failed",
                type(exc).__name__,
            ])
            return fallback_decision

    def _judge(
        self,
        *,
        user_message: str,
        conversation_history: list[dict[str, str]],
        situation: str,
        situation_confidence: float,
        current_memory_snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        api_key, endpoint, model = self._api_config()
        if not api_key:
            raise RuntimeError("missing_memory_router_llm_api_key")

        payload = {
            "model": model,
            "temperature": 1,
            "messages": [
                {"role": "system", "content": self._system_prompt()},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "user_message": user_message,
                            "recent_history": conversation_history[-6:],
                            "situation": situation,
                            "situation_confidence": situation_confidence,
                            "available_memory": self._snapshot_summary(current_memory_snapshot),
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = request.Request(
            endpoint,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )
        with request.urlopen(req, timeout=float(os.getenv("MEMORY_ROUTER_LLM_TIMEOUT", "3.5"))) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        content = (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
            .strip()
        )
        return self._parse_json(content)

    def _api_config(self) -> tuple[str, str, str]:
        api_key = (
            os.getenv("MEMORY_ROUTER_LLM_API_KEY")
            or os.getenv("CHAT_API_KEY")
            or os.getenv("OPENAI_API_KEY")
            or os.getenv("MEMORY_LLM_API_KEY")
            or ""
        ).strip()
        endpoint = (
            os.getenv("MEMORY_ROUTER_LLM_URL")
            or os.getenv("CHAT_API_URL")
            or os.getenv("MEMORY_LLM_URL")
            or ""
        ).strip()
        if not endpoint:
            base_url = (os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
            endpoint = f"{base_url}/chat/completions"
        if endpoint.endswith("/chat/completion"):
            endpoint = endpoint + "s"
        elif not endpoint.endswith("/chat/completions"):
            endpoint = endpoint.rstrip("/") + "/chat/completions"
        model = (
            os.getenv("MEMORY_ROUTER_LLM_MODEL")
            or os.getenv("CHAT_API_MODEL")
            or os.getenv("MEMORY_LLM_MODEL")
            or os.getenv("OPENAI_MODEL")
            or "gpt-4o-mini"
        ).strip()
        return api_key, endpoint, model

    def _system_prompt(self) -> str:
        return (
            "You are a memory routing judge for a companion AI. Decide whether the current user turn "
            "needs long-term memory, which memory tiers to retrieve, and whether the assistant may "
            "explicitly mention remembered facts. Return JSON only. Allowed tiers: profile, "
            "preferences, long_term_goals, episodic_events, safety_notes. retrieval_mode must be "
            "none, background, or explicit. mention_policy must be forbid, implicit_only, or explicit_ok. "
            "Use explicit only when the user asks what the assistant remembers or asks about known personal facts. "
            "Use background for personalized advice/support. Use none for generic tasks, short-term context, "
            "third-party recommendations, or when the user asks not to use memory. Keep max_items small."
        )

    def _parse_json(self, content: str) -> dict[str, Any]:
        if not content:
            raise ValueError("empty_llm_judge_response")
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", content, re.S)
            if not match:
                raise
            parsed = json.loads(match.group(0))
        if not isinstance(parsed, dict):
            raise ValueError("llm_judge_response_not_object")
        return parsed

    def _decision_from_judge(
        self,
        judged: dict[str, Any],
        snapshot: dict[str, Any] | None,
        fallback_decision: MemoryRouteDecision,
    ) -> MemoryRouteDecision:
        if fallback_decision.reason in {
            "user_explicitly_disabled_memory",
            "short_term_context_request",
            "non_user_or_generic_audience",
        }:
            fallback_decision.strategy_version = f"{self.version}_guarded_rule"
            fallback_decision.signals = _dedupe_preserve_order([
                *fallback_decision.signals,
                "llm_judge_guardrail",
            ])
            return fallback_decision

        need_memory = bool(judged.get("need_memory"))
        retrieval_mode = str(judged.get("retrieval_mode") or ("background" if need_memory else "none"))
        if retrieval_mode not in self.ALLOWED_MODES:
            retrieval_mode = "background" if need_memory else "none"

        mention_policy = str(judged.get("mention_policy") or "implicit_only")
        if mention_policy not in self.ALLOWED_MENTION_POLICIES:
            mention_policy = "implicit_only" if need_memory else "forbid"
        if retrieval_mode == "explicit":
            mention_policy = "explicit_ok"
        if not need_memory:
            retrieval_mode = "none"
            mention_policy = "forbid"

        tiers = [
            str(tier)
            for tier in judged.get("tiers", [])
            if str(tier) in self.ALLOWED_TIERS
        ]
        tiers = _dedupe_preserve_order(tiers)
        if snapshot is not None and need_memory:
            available = self.fallback._available_tiers(snapshot)
            tiers = [tier for tier in tiers if tier in available]
            if not tiers and retrieval_mode == "background":
                return self._no_relevant_memory_decision(judged)

        tier_scores = self._tier_scores(judged.get("tier_scores", {}), tiers)
        max_per_tier = self.fallback._limits_for(tiers)
        raw_max_items = judged.get("max_items")
        max_items = self._positive_int(raw_max_items, 0)
        if need_memory and not max_items:
            max_items = sum(max_per_tier.values()) if retrieval_mode == "explicit" else 3

        confidence = self._clamp_float(judged.get("confidence", fallback_decision.confidence))
        signals = [
            "llm_judge",
            *[str(signal) for signal in judged.get("signals", []) if str(signal).strip()],
        ]
        decision = MemoryRouteDecision(
            need_memory=need_memory,
            retrieval_mode=retrieval_mode,
            tiers=tiers,
            max_items=max_items,
            max_per_tier=max_per_tier,
            mention_policy=mention_policy,
            reason=str(judged.get("reason") or "llm_judge_decision"),
            strategy_version=self.version,
            confidence=confidence,
            signals=_dedupe_preserve_order(signals),
            tier_scores=tier_scores,
        )
        if fallback_decision.retrieval_mode == "explicit":
            missing_rule_tiers = [
                tier for tier in fallback_decision.tiers if tier not in decision.tiers
            ]
            if (not decision.need_memory) or decision.retrieval_mode != "explicit" or missing_rule_tiers:
                merged_tiers = _dedupe_preserve_order([*decision.tiers, *fallback_decision.tiers])
                max_per_tier = self.fallback._limits_for(merged_tiers)
                return MemoryRouteDecision(
                    need_memory=True,
                    retrieval_mode="explicit",
                    tiers=merged_tiers,
                    max_items=sum(max_per_tier.values()),
                    max_per_tier=max_per_tier,
                    mention_policy="explicit_ok",
                    reason=fallback_decision.reason,
                    strategy_version=f"{self.version}_guarded_explicit",
                    confidence=max(decision.confidence, fallback_decision.confidence),
                    signals=_dedupe_preserve_order([
                        *decision.signals,
                        *fallback_decision.signals,
                        "llm_judge_guardrail",
                    ]),
                    tier_scores={
                        **decision.tier_scores,
                        **fallback_decision.tier_scores,
                    },
                )
        if fallback_decision.retrieval_mode == "background" and fallback_decision.confidence >= 0.8:
            missing_rule_tiers = [
                tier for tier in fallback_decision.tiers if tier not in decision.tiers
            ]
            if (not decision.need_memory) or decision.retrieval_mode == "none" or missing_rule_tiers:
                merged_tiers = _dedupe_preserve_order([*decision.tiers, *fallback_decision.tiers])
                max_per_tier = self.fallback._limits_for(merged_tiers)
                return MemoryRouteDecision(
                    need_memory=True,
                    retrieval_mode="background",
                    tiers=merged_tiers,
                    max_items=3,
                    max_per_tier=max_per_tier,
                    mention_policy="implicit_only",
                    reason=fallback_decision.reason,
                    strategy_version=f"{self.version}_guarded_background",
                    confidence=max(decision.confidence, fallback_decision.confidence),
                    signals=_dedupe_preserve_order([
                        *decision.signals,
                        *fallback_decision.signals,
                        "llm_judge_guardrail",
                    ]),
                    tier_scores={
                        **decision.tier_scores,
                        **fallback_decision.tier_scores,
                    },
                )
        return decision

    def _no_relevant_memory_decision(self, judged: dict[str, Any]) -> MemoryRouteDecision:
        return MemoryRouteDecision(
            need_memory=False,
            reason=str(judged.get("reason") or "llm_judge_no_relevant_memory_available"),
            strategy_version=self.version,
            confidence=self._clamp_float(judged.get("confidence", 0.85)),
            signals=_dedupe_preserve_order(["llm_judge", "empty_relevant_tiers"]),
        )

    def _tier_scores(self, raw: Any, tiers: list[str]) -> dict[str, float]:
        scores = {tier: 0.0 for tier in self.ALLOWED_TIERS}
        if isinstance(raw, dict):
            for tier, value in raw.items():
                if str(tier) in self.ALLOWED_TIERS:
                    scores[str(tier)] = self._clamp_float(value)
        for tier in tiers:
            scores[tier] = max(scores.get(tier, 0.0), 0.7)
        return {key: round(scores[key], 3) for key in self.fallback.DEFAULT_LIMITS}

    def _positive_int(self, value: Any, default: int) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return default
        return parsed if parsed > 0 else default

    def _clamp_float(self, value: Any) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return 0.0
        return max(0.0, min(1.0, parsed))

    def _snapshot_summary(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        persona = {
            key: value.get("value") if isinstance(value, dict) else value
            for key, value in list((snapshot.get("persona_slots") or {}).items())[:8]
        }
        preferences = {
            key: value.get("value") if isinstance(value, dict) else value
            for key, value in list((snapshot.get("preference_slots") or {}).items())[:8]
        }
        memories = []
        for memory in (snapshot.get("memories") or [])[-8:]:
            if not isinstance(memory, dict):
                continue
            memories.append({
                "memory_type": memory.get("memory_type"),
                "summary": memory.get("summary"),
                "slot_key": memory.get("slot_key"),
                "status": memory.get("status"),
                "tags": memory.get("tags", []),
            })
        return {
            "profile_keys": list(persona.keys()),
            "preference_keys": list(preferences.keys()),
            "persona": persona,
            "preferences": preferences,
            "recent_memories": memories,
        }


def situation_like_food_or_music(lowered: str) -> bool:
    return any(keyword in lowered for keyword in ["喝", "吃", "音乐", "歌", "运动", "散步"])


def situation_like_personal_state(lowered: str) -> bool:
    return any(keyword in lowered for keyword in [
        "累", "烦", "困", "紧张", "焦虑", "孤单", "脑雾", "没动力", "不困",
        "压力", "心情", "提不起劲", "不知道从哪开始",
    ])


class MemoryRouter:
    """Versioned router facade for future memory-routing variants."""

    _STRATEGIES: dict[str, type[MemoryRouterStrategy]] = {
        RuleBasedMemoryRouterV1.version: RuleBasedMemoryRouterV1,
        RuleBasedMemoryRouterV2.version: RuleBasedMemoryRouterV2,
        LLMJudgeMemoryRouterV1.version: LLMJudgeMemoryRouterV1,
    }

    def __init__(self, version: str | None = None):
        version = version or os.getenv("MEMORY_ROUTER_VERSION", RuleBasedMemoryRouterV2.version)
        if version not in self._STRATEGIES:
            raise ValueError(f"Unknown memory router version: {version}")
        self.version = version
        self._strategy = self._STRATEGIES[version]()

    @classmethod
    def register_strategy(cls, version: str, strategy_cls: type[MemoryRouterStrategy]) -> None:
        cls._STRATEGIES[version] = strategy_cls

    def route(
        self,
        *,
        user_message: str,
        conversation_history: list[dict[str, str]] | None = None,
        situation: str = "casual_chat",
        situation_confidence: float = 0.0,
        current_memory_snapshot: dict[str, Any] | None = None,
    ) -> MemoryRouteDecision:
        return self._strategy.route(
            user_message=user_message,
            conversation_history=conversation_history,
            situation=situation,
            situation_confidence=situation_confidence,
            current_memory_snapshot=current_memory_snapshot,
        )
