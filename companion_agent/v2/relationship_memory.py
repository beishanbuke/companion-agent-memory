"""
Relationship Memory Layer

关系感数据层：从对话中学习的长期关系变量。
- comfort_style：用户喜欢被怎么接话
- banter_tolerance：能不能互怼、能怼到什么程度
- advice_threshold：什么时候给建议不会烦
- humor_mode：梗感开关

这些变量从对话中慢慢学出来，不是写死。

偏好持久化规则：
- session_preference：本轮/本次会话临时偏好
- stable_preference：同类偏好出现 3 次以上才长期保存
- explicit_preference：用户明确说"以后都这样"直接持久化
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RelationshipProfile:
    """关系档案（从对话中学习）。"""
    
    # 接话风格偏好
    comfort_style: str = "balanced"  # "gentle"(温柔接话), "direct"(直接吐槽), "balanced"(平衡)
    
    # 互怼容忍度
    banter_tolerance: float = 0.5  # 0-1，越高越能接受互怼
    
    # 建议阈值
    advice_threshold: float = 0.5  # 0-1，越高越能接受建议
    
    # 梗感模式
    humor_mode: str = "light"  # "off"(不玩梗), "light"(轻微), "active"(活跃)
    
    # 学习来源
    evidence: dict[str, list[str]] = field(default_factory=dict)
    
    # 临时会话偏好（不持久化）
    session_preferences: dict[str, Any] = field(default_factory=dict)
    
    # 偏好出现计数（用于稳定化判断）
    preference_counts: dict[str, int] = field(default_factory=dict)
    
    # 版本
    version: int = 0


class RelationshipMemory:
    """关系感记忆层（从对话中学习用户偏好）。"""
    
    # 稳定化阈值：同类信号出现多少次才写入长期档案
    STABLE_THRESHOLD = 3
    
    def __init__(self):
        self._profiles: dict[str, RelationshipProfile] = {}  # session_id -> profile
    
    def _get_or_create(self, session_id: str) -> RelationshipProfile:
        """获取或创建关系档案。"""
        if session_id not in self._profiles:
            self._profiles[session_id] = RelationshipProfile()
        return self._profiles[session_id]
    
    def _update_preference(
        self,
        profile: RelationshipProfile,
        key: str,
        new_value: Any,
        explicit: bool = False,
    ) -> bool:
        """更新偏好，返回是否写入长期档案。
        
        Rules:
        - explicit=True: 直接写入长期档案
        - explicit=False: 先计入 session_preferences，达到 STABLE_THRESHOLD 才持久化
        """
        if explicit:
            setattr(profile, key, new_value)
            profile.evidence.setdefault(key, []).append(f"用户明确要求: {new_value}")
            return True
        
        # 先放入 session_preferences
        old_session = profile.session_preferences.get(key)
        profile.session_preferences[key] = new_value
        
        # 如果和上次 session 值相同，计数+1
        if old_session == new_value:
            profile.preference_counts[key] = profile.preference_counts.get(key, 0) + 1
        else:
            # 偏好变化，重置计数
            profile.preference_counts[key] = 1
        
        # 达到稳定阈值才持久化
        if profile.preference_counts.get(key, 0) >= self.STABLE_THRESHOLD:
            setattr(profile, key, new_value)
            profile.evidence.setdefault(key, []).append(
                f"连续{self.STABLE_THRESHOLD}次出现，稳定化: {new_value}"
            )
            # 清空 session 记录
            profile.session_preferences.pop(key, None)
            profile.preference_counts[key] = 0
            return True
        
        return False
    
    def learn_from_interaction(
        self,
        user_message: str,
        assistant_reply: str,
        intent: Any,
        session_id: str = "",
    ) -> RelationshipProfile:
        """从一次互动中学习关系偏好。
        
        学习信号：
        - 用户对回复的反馈（隐式：继续聊/转移话题/结束对话）
        - 用户主动要求改变风格
        - 对话模式持续时间
        """
        profile = self._get_or_create(session_id)
        
        # === 学习 comfort_style ===
        explicit = any(kw in user_message for kw in ["以后直接说", "以后别哄我", "以后温柔点"])
        if any(kw in user_message for kw in ["太温柔", "别哄我", "直接说"]):
            self._update_preference(profile, "comfort_style", "direct", explicit=explicit)
            profile.evidence.setdefault("comfort_style", []).append("用户要求直接说")
        elif any(kw in user_message for kw in ["抱抱", "安慰", "别说了"]):
            self._update_preference(profile, "comfort_style", "gentle", explicit=explicit)
            profile.evidence.setdefault("comfort_style", []).append("用户需要安慰")
        
        # === 学习 banter_tolerance ===
        if intent.conversation_rhythm == "bantering":
            if intent.emotional_intensity < 0.3:
                self._update_preference(
                    profile, "banter_tolerance",
                    min(1.0, profile.banter_tolerance + 0.05),
                    explicit=False,
                )
                profile.evidence.setdefault("banter_tolerance", []).append("用户持续互怼")
        elif any(kw in user_message for kw in ["认真点", "别闹", "正经点"]):
            self._update_preference(
                profile, "banter_tolerance",
                max(0.1, profile.banter_tolerance - 0.1),
                explicit=False,
            )
            profile.evidence.setdefault("banter_tolerance", []).append("用户要求正经")
        
        # === 学习 advice_threshold ===
        explicit_advice = any(kw in user_message for kw in ["以后别给建议", "以后多给建议", "记住我喜欢"])
        if intent.primary_intent == "advice" and intent.task_urgency > 0.5:
            self._update_preference(
                profile, "advice_threshold",
                min(1.0, profile.advice_threshold + 0.03),
                explicit=explicit_advice,
            )
            profile.evidence.setdefault("advice_threshold", []).append("用户主动求助")
        elif any(kw in user_message for kw in ["别教我", "我知道", "别建议"]):
            self._update_preference(
                profile, "advice_threshold",
                max(0.1, profile.advice_threshold - 0.1),
                explicit=explicit_advice,
            )
            profile.evidence.setdefault("advice_threshold", []).append("用户拒绝建议")
        
        # === 学习 humor_mode ===
        if intent.conversation_rhythm == "bantering":
            if profile.humor_mode == "off":
                self._update_preference(profile, "humor_mode", "light", explicit=False)
            elif profile.humor_mode == "light":
                self._update_preference(profile, "humor_mode", "active", explicit=False)
            profile.evidence.setdefault("humor_mode", []).append("用户主动玩梗")
        elif intent.emotional_intensity > 0.7 and intent.primary_intent in ("companion", "vent"):
            # 情绪高时降梗
            if profile.humor_mode == "active":
                self._update_preference(profile, "humor_mode", "light", explicit=False)
            profile.evidence.setdefault("humor_mode", []).append("情绪高时降梗")
        
        profile.version += 1
        
        # 清理旧证据（只保留最近 20 条）
        for key in profile.evidence:
            if len(profile.evidence[key]) > 20:
                profile.evidence[key] = profile.evidence[key][-20:]
        
        return profile
    
    def get_profile(self, session_id: str = "") -> RelationshipProfile:
        """获取关系档案。"""
        return self._get_or_create(session_id)
    
    def get_humor_mode(
        self,
        emotional_intensity: float,
        conversation_mode: str,
        session_id: str = "",
    ) -> str:
        """获取当前梗感模式。
        
        综合考虑：
        - 用户长期偏好
        - 当前情绪强度（情绪高时降梗）
        - 当前对话模式（认真规划时降梗）
        """
        profile = self._get_or_create(session_id)
        base_mode = profile.humor_mode
        
        # 情绪高时强制降梗
        if emotional_intensity > 0.7:
            if base_mode == "active":
                return "light"
            elif base_mode == "light":
                return "off"
            return "off"
        
        # 认真规划时降梗
        if conversation_mode == "planning":
            if base_mode == "active":
                return "light"
            return base_mode
        
        return base_mode
    
    def should_give_advice(
        self,
        user_emotional_state: str,
        task_urgency: float,
        session_id: str = "",
    ) -> bool:
        """判断当前是否适合给建议。
        
        综合考虑：
        - 用户建议阈值
        - 情绪状态（情绪高时不给建议）
        - 任务紧急度
        """
        profile = self._get_or_create(session_id)
        
        # 情绪高时不给建议
        if user_emotional_state in ("sad", "anxious", "angry") and task_urgency < 0.7:
            return False
        
        # 阈值判断
        return task_urgency > (1.0 - profile.advice_threshold)
    
    def get_summary(self, session_id: str = "") -> dict[str, Any]:
        """获取关系档案摘要。"""
        profile = self._get_or_create(session_id)
        return {
            "comfort_style": profile.comfort_style,
            "banter_tolerance": round(profile.banter_tolerance, 2),
            "advice_threshold": round(profile.advice_threshold, 2),
            "humor_mode": profile.humor_mode,
            "version": profile.version,
            "session_preferences": profile.session_preferences,
            "preference_counts": profile.preference_counts,
        }