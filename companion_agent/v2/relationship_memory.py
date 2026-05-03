"""
Relationship Memory Layer

关系感数据层：从对话中学习的长期关系变量。
- comfort_style：用户喜欢被怎么接话
- banter_tolerance：能不能互怼、能怼到什么程度
- advice_threshold：什么时候给建议不会烦
- humor_mode：梗感开关

这些变量从对话中慢慢学出来，不是写死。
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
    
    # 版本
    version: int = 0


class RelationshipMemory:
    """关系感记忆层（从对话中学习用户偏好）。"""
    
    def __init__(self):
        self._profiles: dict[str, RelationshipProfile] = {}  # session_id -> profile
    
    def _get_or_create(self, session_id: str) -> RelationshipProfile:
        """获取或创建关系档案。"""
        if session_id not in self._profiles:
            self._profiles[session_id] = RelationshipProfile()
        return self._profiles[session_id]
    
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
        if any(kw in user_message for kw in ["太温柔", "别哄我", "直接说"]):
            profile.comfort_style = "direct"
            profile.evidence.setdefault("comfort_style", []).append("用户要求直接说")
        elif any(kw in user_message for kw in ["抱抱", "安慰", "别说了"]):
            profile.comfort_style = "gentle"
            profile.evidence.setdefault("comfort_style", []).append("用户需要安慰")
        
        # === 学习 banter_tolerance ===
        if intent.conversation_rhythm == "bantering":
            # 如果用户在犯贱/互怼模式中持续多轮，说明容忍度高
            if intent.emotional_intensity < 0.3:
                profile.banter_tolerance = min(1.0, profile.banter_tolerance + 0.05)
                profile.evidence.setdefault("banter_tolerance", []).append("用户持续互怼")
        elif any(kw in user_message for kw in ["认真点", "别闹", "正经点"]):
            profile.banter_tolerance = max(0.1, profile.banter_tolerance - 0.1)
            profile.evidence.setdefault("banter_tolerance", []).append("用户要求正经")
        
        # === 学习 advice_threshold ===
        if intent.primary_intent == "advice" and intent.task_urgency > 0.5:
            # 用户主动求助且急，说明接受建议
            profile.advice_threshold = min(1.0, profile.advice_threshold + 0.03)
            profile.evidence.setdefault("advice_threshold", []).append("用户主动求助")
        elif any(kw in user_message for kw in ["别教我", "我知道", "别建议"]):
            profile.advice_threshold = max(0.1, profile.advice_threshold - 0.1)
            profile.evidence.setdefault("advice_threshold", []).append("用户拒绝建议")
        
        # === 学习 humor_mode ===
        if intent.conversation_rhythm == "bantering":
            if profile.humor_mode == "off":
                profile.humor_mode = "light"
            elif profile.humor_mode == "light":
                profile.humor_mode = "active"
            profile.evidence.setdefault("humor_mode", []).append("用户主动玩梗")
        elif intent.emotional_intensity > 0.7 and intent.primary_intent in ("companion", "vent"):
            # 情绪高时降梗
            if profile.humor_mode == "active":
                profile.humor_mode = "light"
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
        }