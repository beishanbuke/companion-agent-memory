"""
Policy Planner

升级自 DualBrainRouter，从二元 chat/task 变成显式 turn policy。

每轮策略决策，输出固定 schema：
- goal: stabilize|push_one_step|review_day|resume_main_thread|stay_light|clarify_urgency
- pull_main_thread: 是否拉回主线
- clarify_needed: 是否需要澄清
- max_questions: 最多几个问题
- max_actions: 最多几个行动
- allow_humor: 是否允许玩梗
- allow_advice: 是否允许给建议
- tool_calls: 工具调用列表
- response_length: short|medium|long
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TurnPolicy:
    """单轮策略决策。"""
    # 核心目标
    goal: str = "stay_light"  # stabilize/push_one_step/review_day/resume_main_thread/stay_light/clarify_urgency
    
    # 主线管理
    pull_mode: str = "silent"  # silent/soft/active
    pull_main_thread: bool = False
    main_thread_id: str = ""
    
    # 交互控制
    clarify_needed: bool = False
    max_questions: int = 1
    max_actions: int = 1
    
    # 表达控制
    allow_humor: bool = True
    allow_advice: bool = False
    allow_recap: bool = False
    response_length: str = "short"  # short/medium/long

    # 工具
    tool_calls: list[str] = field(default_factory=list)
    context_profile: str = "standard"  # minimal/standard/task_heavy/thread_resume/review
  
    # 状态机目标
    target_state: str = ""
    
    # 原因
    reason: str = ""

    # 技能输出控制
    skill_verbosity: str = "hint"  # hint/short/card/full


class PolicyPlanner:
    """策略规划器（升级自 DualBrainRouter）。"""

    @staticmethod
    def _rel_get(profile: Any, key: str, default: Any) -> Any:
        if isinstance(profile, dict):
            return profile.get(key, default)
        return getattr(profile, key, default)
    
    def plan(
        self,
        intent: Any,
        state: Any,
        thread_manager: Any,
        relationship_profile: Any,
        user_message: str = "",
    ) -> TurnPolicy:
        """规划本轮策略。
        
        输入：
        - intent: 意图分析结果
        - state: 当前对话状态
        - thread_manager: 主线管理器
        - relationship_profile: 关系画像
        """
        
        policy = TurnPolicy()
        msg = user_message or ""
        
        # === 1. 判断主线拉回模式 ===
        pull_mode, target_id = thread_manager.should_pull_main_thread(getattr(state, "session_id", ""))
        
        # 默认 silent，不主动拉回
        policy.pull_mode = "silent"
        policy.main_thread_id = target_id
        
        # 只有当用户明确提到相关线索或要求复盘时才 soft/active
        user_asks_review = any(w in msg for w in ["复习", "复盘", "回顾", "提醒", "那个事", "之前"])
        user_mentions_related = target_id and any(
            kw in msg for kw in ["考试", "ddl", "论文", "工作", "压力", "复习", "准备"]
        )
        
        if pull_mode == "soft" and (user_asks_review or user_mentions_related):
            policy.pull_mode = "soft"
            policy.goal = "resume_main_thread"
            policy.reason = f"用户提及相关线索，轻提醒后台主线: {target_id}"
            policy.max_questions = 0
            policy.allow_humor = False
            policy.response_length = "short"
            policy.context_profile = "standard"
            # soft 模式下不正式切换前台主线，只在回复中轻提一句
            policy.pull_main_thread = False
            return policy
        elif user_asks_review and target_id:
            # 用户明确要求复盘，可以 active
            policy.pull_mode = "active"
            policy.pull_main_thread = True
            policy.goal = "resume_main_thread"
            policy.reason = f"用户主动要求复盘主线: {target_id}"
            policy.max_questions = 0
            policy.allow_humor = False
            policy.response_length = "medium"
            policy.context_profile = "thread_resume"
            return policy
        
        # === 2. 根据意图和状态决定策略 ===
        
        # 高压情绪 -> stabilize
        if intent.emotional_intensity > 0.8:
            policy.goal = "stabilize"
            policy.target_state = "support_crisis"
            policy.allow_advice = False
            policy.allow_humor = False
            policy.max_questions = 0
            policy.max_actions = 0
            policy.response_length = "short"
            policy.context_profile = "minimal"
            policy.skill_verbosity = "hint"
            policy.reason = "用户情绪高强度，优先稳定"
            return policy
        
        # 中等情绪 + 可推动 -> push_one_step
        if intent.emotional_intensity > 0.4 and intent.emotional_intensity <= 0.7:
            if intent.action_receptivity > 0.5:
                policy.goal = "push_one_step"
                policy.target_state = "pushable_low_energy"
                policy.allow_advice = True
                policy.max_questions = 0
                policy.max_actions = 1
                policy.response_length = "medium"
                policy.context_profile = "standard"
                policy.skill_verbosity = "short"
                policy.reason = "用户情绪中等，有一定承接力，可轻推一步"
                return policy
        
        # 明确任务 + 紧急 -> task_execution
        if intent.primary_intent == "execute" and intent.task_urgency > 0.6:
            policy.goal = "push_one_step"
            policy.target_state = "task_execution"
            policy.allow_advice = True
            policy.max_questions = 0
            policy.tool_calls = [intent.task_category] if intent.task_category != "none" else []
            policy.response_length = "medium"
            policy.context_profile = "task_heavy"
            policy.skill_verbosity = "card" if intent.action_receptivity > 0.7 else "short"
            policy.reason = f"用户明确执行任务，紧急度{intent.task_urgency:.1f}"
            return policy
        
        # 主动复盘 -> review_day
        msg = user_message or ""
        if intent.conversation_rhythm == "reviewing" or any(word in msg for word in ["总结", "复盘", "回顾", "梳理一下"]):
            review_scope = "day"
            if any(word in msg for word in ["这周", "本周", "一周"]):
                review_scope = "week"
            elif any(word in msg for word in ["这阶段", "这学期", "最近这段时间", "这个阶段"]):
                review_scope = "phase"
            policy.goal = f"review_{review_scope}"
            policy.target_state = "review_reflection"
            policy.allow_advice = False
            policy.allow_recap = True
            policy.max_questions = 1
            policy.response_length = "medium"
            policy.context_profile = "review"
            policy.skill_verbosity = "short"
            policy.reason = f"用户主动{review_scope}复盘"
            return policy
        
        # 话题切换识别
        if intent.topic_shift_type in ("new_thread", "functional_detour"):
            if intent.pressure_signal > 0.6:
                # 高压话题切换，需要澄清
                policy.goal = "clarify_urgency"
                policy.clarify_needed = True
                policy.max_questions = 1
                policy.response_length = "short"
                policy.context_profile = "minimal"
                policy.skill_verbosity = "hint"
                policy.reason = "检测到高压话题切换，需要确认紧急度"
                return policy
        
        # 闲聊/犯贱 -> stay_light
        if intent.conversation_rhythm in ("bantering", "chill", "sharing"):
            policy.goal = "stay_light"
            policy.target_state = "light_chat"
            policy.allow_humor = self._rel_get(relationship_profile, "humor_mode", "light") != "off"
            policy.allow_advice = False
            policy.max_questions = 0
            policy.response_length = "short"
            policy.context_profile = "standard"
            policy.skill_verbosity = "hint"
            policy.reason = "轻松闲聊模式"
            return policy
        
        # 倾诉 -> support_soft
        if intent.conversation_rhythm == "confiding":
            policy.goal = "stabilize"
            policy.target_state = "support_soft"
            policy.allow_advice = self._rel_get(relationship_profile, "advice_threshold", 0.5) > 0.7
            policy.allow_humor = False
            policy.max_questions = 0
            policy.response_length = "medium"
            policy.context_profile = "standard"
            policy.skill_verbosity = "hint"
            policy.reason = "用户在倾诉"
            return policy
        
        # 规划 -> planning
        if intent.conversation_rhythm == "planning" or intent.primary_intent == "advice":
            policy.goal = "push_one_step"
            policy.target_state = "planning"
            policy.allow_advice = True
            policy.max_questions = 0
            policy.max_actions = 1
            policy.response_length = "medium"
            policy.context_profile = "task_heavy"
            policy.skill_verbosity = "card" if intent.action_receptivity > 0.6 else "short"
            policy.reason = "用户在做规划"
            return policy
        
        # 默认
        policy.goal = "stay_light"
        policy.target_state = "light_chat"
        policy.context_profile = "standard"
        policy.reason = "默认策略"
        return policy
    
    def get_mode_from_policy(self, policy: TurnPolicy) -> str:
        """从策略推断模式（兼容旧接口）。"""
        if policy.goal in ("stabilize", "stay_light"):
            return "chat"
        elif policy.goal in ("push_one_step", "resume_main_thread", "review_day", "review_week", "review_phase"):
            return "task" if policy.tool_calls else "chat"
        elif policy.goal == "clarify_urgency":
            return "chat"
        return "chat"
    
    def should_ask_question(self, policy: TurnPolicy, state: Any) -> bool:
        """判断本轮是否应该提问。"""
        if policy.max_questions <= 0:
            return False
        
        # 如果已经连续问了2轮，本轮不问
        if state.mode_duration > 2 and state.mode in ("support", "confiding"):
            return False
        
        return True
