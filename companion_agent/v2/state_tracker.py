"""
State Tracker v2

隐式状态跟踪器（支持会话隔离和生命周期管理）。
不每轮从零分类，而是维护连续对话状态：
- 当前对话模式（吐槽 / 倾诉 / 犯贱 / 认真规划 / 日常闲聊）
- 情绪趋势（情绪在升温 / 降温 / 稳定）
- 用户状态（用户在哪种生活场景中）
- 关系亲密度趋势

状态生命周期规则：
- 会话重置：清空所有状态
- 角色切换：保留情绪趋势和亲密度，重置模式和待办
- 模型切换：不影响状态
- 多端并发：按 session_id 隔离
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# 显式状态机状态
STATE_LIGHT_CHAT = "light_chat"          # 日常闲聊
STATE_SUPPORT_CRISIS = "support_crisis"  # 情绪危机/深度陪伴
STATE_SUPPORT_SOFT = "support_soft"      # 软陪伴/倾诉承接
STATE_PUSHABLE_LOW = "pushable_low_energy"  # 低能量但可被轻推
STATE_TASK_EXEC = "task_execution"       # 任务执行中
STATE_TASK_DONE = "task_done"            # 任务刚完成
STATE_PLANNING = "planning"              # 认真规划
STATE_REVIEW_REFLECTION = "review_reflection"  # 复盘收拢
STATE_QUIET = "quiet"                    # 用户想安静
STATE_CLARIFY = "clarify"                # 需要澄清


@dataclass
class ConversationState:
    """当前对话状态（显式状态机版）。"""
    # 会话标识
    session_id: str = "default"
    character_id: str = ""  # 当前角色卡 ID
    
    # 显式状态机状态
    current_state: str = STATE_LIGHT_CHAT
    state_duration: int = 0
    previous_state: str = ""
    
    # 对话模式（连续状态，保留用于兼容性）
    mode: str = "casual"
    mode_confidence: float = 0.5
    mode_duration: int = 0
    
    # 情绪趋势
    emotional_trend: str = "stable"
    dominant_emotion: str = "neutral"
    emotion_history: list[tuple[str, float]] = field(default_factory=list)
    
    # 用户生活场景
    user_scene: str = ""
    
    # 关系亲密度（动态变化）
    intimacy_level: float = 0.5
    intimacy_trend: str = "stable"
    
    # 最近话题
    recent_topics: list[str] = field(default_factory=list)
    
    # 未完成的互动
    pending_question: str = ""
    pending_task: str = ""
    
    # 时间上下文
    last_message_time: str = ""
    time_of_day: str = ""
    
    # 状态版本（用于检测变更）
    version: int = 0


class StateTracker:
    """跟踪和管理对话隐式状态（支持多会话隔离）。"""
    
    def __init__(self):
        self._states: dict[str, ConversationState] = {}  # session_id -> state
        self._default_session = "default"
        self._max_history = 10
        self._max_sessions = 100  # 防止内存泄漏
    
    def _get_or_create_state(self, session_id: str) -> ConversationState:
        """获取或创建会话状态。"""
        if session_id not in self._states:
            # 清理旧会话（LRU）
            if len(self._states) >= self._max_sessions:
                oldest = min(self._states.keys(), key=lambda k: self._states[k].version)
                del self._states[oldest]
            
            self._states[session_id] = ConversationState(session_id=session_id)
        
        return self._states[session_id]
    
    @property
    def state(self) -> ConversationState:
        """获取默认会话状态（向后兼容）。"""
        return self._get_or_create_state(self._default_session)
    
    def reset_session(self, session_id: str = "", full_reset: bool = True) -> None:
        """重置会话状态。
        
        Args:
            session_id: 会话 ID，空字符串表示默认会话
            full_reset: 是否完全重置（True=全部清空，False=软重置保留亲密度基线）
        """
        sid = session_id or self._default_session
        
        if sid not in self._states:
            return
        
        old_state = self._states[sid]
        
        if full_reset:
            # 完全重置：清空所有状态
            self._states[sid] = ConversationState(session_id=sid)
        else:
            # 软重置：保留亲密度基线和情绪基线，重置模式和话题
            self._states[sid] = ConversationState(
                session_id=sid,
                character_id=old_state.character_id,
                intimacy_level=max(0.3, old_state.intimacy_level * 0.7),  # 亲密度衰减
                dominant_emotion=old_state.dominant_emotion,  # 保留主导情绪
            )
    
    def switch_character(self, session_id: str, character_id: str) -> None:
        """切换角色卡时的状态处理。
        
        规则：
        - 保留情绪趋势和亲密度（关系是跟人，不是跟角色）
        - 重置对话模式、话题、待办（不同角色不同语境）
        """
        sid = session_id or self._default_session
        state = self._get_or_create_state(sid)
        
        # 保存关系数据
        intimacy = state.intimacy_level
        emotion = state.dominant_emotion
        
        # 重置（软重置）
        self.reset_session(sid, full_reset=False)
        
        # 恢复关系数据
        new_state = self._get_or_create_state(sid)
        new_state.intimacy_level = intimacy
        new_state.dominant_emotion = emotion
        new_state.character_id = character_id
    
    def _transition_state(
        self,
        intent: Any,
        state: ConversationState,
    ) -> None:
        """显式状态机：基于意图信号决定状态转移。"""
        old_state = state.current_state
        new_state = old_state
        
        # 信号提取
        pressure = getattr(intent, "pressure_signal", 0.0)
        action_rec = getattr(intent, "action_receptivity", 0.5)
        shift_type = getattr(intent, "topic_shift_type", "none")
        emotion_intensity = intent.emotional_intensity
        primary = intent.primary_intent
        task_urgency = intent.task_urgency
        clarification = getattr(intent, "clarification_confidence", 0.0)
        
        # === 状态转移规则 ===
        
        # 1. 高压力/情绪危机 -> support_crisis
        if emotion_intensity > 0.7 and primary in ("companion", "vent", "share"):
            new_state = STATE_SUPPORT_CRISIS
        
        # 2. 软陪伴/倾诉承接 -> support_soft
        elif primary in ("companion", "share", "vent") and intent.conversation_rhythm == "confiding":
            new_state = STATE_SUPPORT_SOFT

        # 3. 低能量但可被轻推 -> pushable_low
        elif emotion_intensity > 0.4 and action_rec > 0.3 and action_rec < 0.6 and task_urgency < 0.5:
            new_state = STATE_PUSHABLE_LOW
        
        # 4. 主动复盘 -> review_reflection
        elif intent.conversation_rhythm == "reviewing":
            new_state = STATE_REVIEW_REFLECTION

        # 5. 规划态 -> planning
        elif intent.conversation_rhythm == "planning" or primary == "advice":
            new_state = STATE_PLANNING

        # 6. 任务执行中 -> task_exec
        elif primary == "execute" or (task_urgency > 0.5 and action_rec > 0.5):
            new_state = STATE_TASK_EXEC
        
        # 7. 需要澄清 -> clarify
        elif clarification > 0.6:
            new_state = STATE_CLARIFY
        
        # 8. 用户想安静 -> quiet
        elif primary == "quiet":
            new_state = STATE_QUIET
        
        # 9. 话题回归/新主线 -> light_chat (如果情绪稳定)
        elif shift_type in ("return_to_thread", "new_thread") and emotion_intensity < 0.5:
            new_state = STATE_LIGHT_CHAT
        
        # 10. 默认回 light_chat (情绪稳定)
        elif emotion_intensity < 0.4 and state.current_state != STATE_TASK_EXEC:
            new_state = STATE_LIGHT_CHAT
        
        # 8. 任务完成后过渡
        if old_state == STATE_TASK_EXEC and new_state != STATE_TASK_EXEC:
            new_state = STATE_TASK_DONE
        
        # 应用状态转移
        if new_state != old_state:
            state.previous_state = old_state
            state.current_state = new_state
            state.state_duration = 1
        else:
            state.state_duration += 1
        
        # 同步更新 mode (兼容旧逻辑)
        state.mode = self._infer_mode(intent)
    
    def update(
        self,
        intent_analysis: Any,
        user_message: str,
        assistant_reply: str = "",
        session_id: str = "",
    ) -> ConversationState:
        """基于意图分析和消息更新状态（支持会话隔离）。"""
        sid = session_id or self._default_session
        state = self._get_or_create_state(sid)
        
        # 版本递增
        state.version += 1
        
        # === 显式状态机转移 ===
        self._transition_state(intent_analysis, state)
        
        # === 更新对话模式（兼容旧逻辑） ===
        new_mode = self._infer_mode(intent_analysis)
        if new_mode == state.mode:
            state.mode_duration += 1
        else:
            state.mode = new_mode
            state.mode_duration = 1
        
        # === 更新情绪历史 ===
        state.emotion_history.append(
            (intent_analysis.emotional_state, intent_analysis.emotional_intensity)
        )
        if len(state.emotion_history) > self._max_history:
            state.emotion_history = state.emotion_history[-self._max_history:]
        
        # === 计算情绪趋势 ===
        state.dominant_emotion = self._calc_dominant_emotion(state)
        state.emotional_trend = self._calc_emotion_trend(state)
        
        # === 更新生活场景 ===
        state.user_scene = self._infer_scene(intent_analysis, user_message, state)
        
        # === 更新亲密度 ===
        self._update_intimacy(intent_analysis, user_message, assistant_reply, state)
        
        # === 更新话题 ===
        topic = intent_analysis.task_category if intent_analysis.task_category != "none" else intent_analysis.primary_intent
        if topic and topic not in state.recent_topics:
            state.recent_topics.append(topic)
            if len(state.recent_topics) > 5:
                state.recent_topics = state.recent_topics[-5:]
        
        # === 检测未完成的互动 ===
        self._detect_pending_interactions(user_message, assistant_reply, state)
        
        return state
    

    
    def _infer_mode(self, intent: Any) -> str:
        """从意图推断对话模式。"""
        rhythm = intent.conversation_rhythm
        primary = intent.primary_intent
        
        mapping = {
            "venting": "venting",
            "confiding": "confiding",
            "bantering": "bantering",
            "seeking_help": "planning" if intent.task_urgency > 0.5 else "casual",
            "sharing": "casual",
            "chill": "casual",
            "planning": "planning",
            "reviewing": "review",
        }
        
        mode = mapping.get(rhythm, "casual")
        
        # 特殊处理：如果用户明确想安静
        if primary == "quiet":
            mode = "quiet"
        
        # 特殊处理：高强度情绪 + 需要陪伴
        if intent.emotional_intensity > 0.7 and primary == "companion":
            mode = "support"
        
        return mode
    
    def _calc_dominant_emotion(self, state: ConversationState) -> str:
        """计算主导情绪。"""
        if not state.emotion_history:
            return "neutral"
        
        recent = state.emotion_history[-3:]
        emotions = [e[0] for e in recent]
        
        from collections import Counter
        counts = Counter(emotions)
        return counts.most_common(1)[0][0]
    
    def _calc_emotion_trend(self, state: ConversationState) -> str:
        """计算情绪趋势。"""
        if len(state.emotion_history) < 3:
            return "stable"
        
        recent = state.emotion_history[-3:]
        intensities = [e[1] for e in recent]
        
        if intensities[-1] - intensities[0] > 0.2:
            return "rising"
        elif intensities[0] - intensities[-1] > 0.2:
            return "falling"
        else:
            return "stable"
    
    def _infer_scene(self, intent: Any, message: str, state: ConversationState) -> str:
        """推断用户当前生活场景。"""
        t = message.lower()
        
        if intent.task_category == "study" or any(kw in t for kw in ["图书馆", "教室", "复习", "作业", "考试", "学习"]):
            return "study"
        elif intent.task_category == "food" or any(kw in t for kw in ["吃饭", "食堂", "外卖", "饿了", "吃什么"]):
            return "meal"
        elif any(kw in t for kw in ["睡觉", "躺", "休息", "宿舍", "寝室", "累死了"]):
            return "rest"
        elif intent.task_category == "social" or any(kw in t for kw in ["朋友", "同学", "约会", "聚会", "社交"]):
            return "social"
        elif any(kw in t for kw in ["上课", "教室", "走去", "骑车", "地铁", "公交"]):
            return "commute"
        
        return state.user_scene or "unknown"
    
    def _update_intimacy(
        self,
        intent: Any,
        user_message: str,
        assistant_reply: str,
        state: ConversationState,
    ) -> None:
        """更新关系亲密度。"""
        old_intimacy = state.intimacy_level
        
        warming_signals = [
            intent.conversation_rhythm == "confiding",
            any(kw in user_message for kw in ["谢谢你", "你真好", "懂我", "只有你"]),
            len(user_message) > 50 and intent.emotional_intensity > 0.5,
            getattr(intent, "pressure_signal", 0.0) < 0.3 and intent.emotional_intensity > 0.4,
        ]
        
        cooling_signals = [
            intent.primary_intent == "execute" and intent.task_urgency > 0.7,
            any(kw in user_message for kw in ["算了", "不用了", "我自己来", "别问了"]),
            getattr(intent, "topic_shift_type", "none") == "emotional_escape",
            getattr(intent, "pressure_signal", 0.0) > 0.6,
        ]
        
        if any(warming_signals):
            state.intimacy_level = min(1.0, old_intimacy + 0.03)
            state.intimacy_trend = "warming"
        elif any(cooling_signals):
            state.intimacy_level = max(0.1, old_intimacy - 0.02)
            state.intimacy_trend = "cooling"
        else:
            state.intimacy_trend = "stable"
    
    def _detect_pending_interactions(self, user_message: str, assistant_reply: str, state: ConversationState) -> None:
        """检测未完成的互动。"""
        if assistant_reply and "?" in assistant_reply[-30:]:
            state.pending_question = assistant_reply[-50:]
        else:
            state.pending_question = ""
        
        t = user_message.lower()
        if any(kw in t for kw in ["明天要", "记得", "别忘了", "待会要", "等下要"]):
            state.pending_task = user_message[:50]
    
    def get_state_summary(self, session_id: str = "") -> dict[str, Any]:
        """获取状态摘要（用于提示词）。"""
        state = self._get_or_create_state(session_id or self._default_session)
        return {
            "current_state": state.current_state,
            "state_duration": state.state_duration,
            "previous_state": state.previous_state,
            "mode": state.mode,
            "mode_duration": state.mode_duration,
            "dominant_emotion": state.dominant_emotion,
            "emotional_trend": state.emotional_trend,
            "user_scene": state.user_scene,
            "intimacy_level": round(state.intimacy_level, 2),
            "recent_topics": state.recent_topics,
            "pending_question": state.pending_question,
        }
    
    def should_stay_in_chat_mode(self, intent: Any, session_id: str = "") -> bool:
        """判断当前是否应保持在 chat mode（基于显式状态机）。"""
        state = self._get_or_create_state(session_id or self._default_session)
        
        # 显式状态中，这些状态强制保持 chat mode
        if state.current_state in (STATE_SUPPORT_CRISIS, STATE_SUPPORT_SOFT, STATE_PUSHABLE_LOW, STATE_QUIET, STATE_REVIEW_REFLECTION):
            return True
        
        if intent.emotional_intensity > 0.6 and intent.primary_intent in ("companion", "vent", "share"):
            return True
        
        if state.mode in ("venting", "confiding", "bantering"):
            return True
        
        if intent.task_urgency < 0.4 and state.mode_duration > 2:
            return True
        
        return False
    
    def get_state_guidance(self, session_id: str = "") -> str:
        """获取当前显式状态的对话指导。"""
        state = self._get_or_create_state(session_id or self._default_session)
        guidance = {
            # 显式状态
            STATE_LIGHT_CHAT: "普通闲聊。自然接话，偶尔抛个小话题。",
            STATE_SUPPORT_CRISIS: "用户情绪危机。优先陪伴，不急于解决问题。让用户感到被接纳。不要给建议。",
            STATE_SUPPORT_SOFT: "用户在认真倾诉。先承接和整理感受，再决定是否轻轻推进。",
            STATE_PUSHABLE_LOW: "用户低能量但可被轻推。先共情，再试探性给一个小建议。不要push太狠。",
            STATE_TASK_EXEC: "任务执行中。专注帮用户完成任务，保持高效。完成后自然过渡。",
            STATE_TASK_DONE: "任务刚完成。给用户一个正向反馈，然后自然回到闲聊或询问是否还有别的。",
            STATE_PLANNING: "用户在认真规划。聚焦优先级、下一步和现实约束，少废话。",
            STATE_REVIEW_REFLECTION: "用户在复盘。先帮他收拢今天/这周/这个阶段，再提炼卡点和下一步。",
            STATE_QUIET: "用户想安静。回复要短，不要追问。给一个温暖的收尾。",
            STATE_CLARIFY: "需要澄清。礼貌地请用户说明白一点。不要猜测太多。",
            # 兼容旧 mode
            "venting": "用户在吐槽/发泄。不要给建议，先接话。可以说'确实'、'懂的'、'这也太...'。让用户说完。",
            "confiding": "用户在倾诉。回应要轻，不要追问太多。表示理解和接纳。",
            "bantering": "用户在犯贱/互怼。可以轻微回怼，但要保持善意底线。不要真的冒犯。",
            "planning": "用户在认真规划。可以给出具体建议，但保持朋友口吻，不要变成客服。",
            "support": "用户需要情绪支持。优先陪伴，不急于解决问题。让用户感到被接纳。",
            "quiet": "用户想安静。回复要短，不要追问。给一个温暖的收尾。",
            "casual": "普通闲聊。自然接话，偶尔抛个小话题。",
        }
        # 优先返回显式状态指导
        return guidance.get(state.current_state, guidance.get(state.mode, ""))
    
    def get_mode_guidance(self, session_id: str = "") -> str:
        """获取当前模式的对话指导（向后兼容）。"""
        return self.get_state_guidance(session_id)
