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
    allow_micro_action: bool = False  # 允许一个非常小的当前动作（如"先写标题"）
    allow_direct_pick: bool = False   # 允许直接替用户做选择（如"吃牛肉面"）
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

    # 硬约束列表
    hard_constraints: list[str] = field(default_factory=list)


def enforce_max_questions(reply_text: str, max_q: int) -> dict[str, Any]:
    """Count '?' in reply and log warning if exceeded.
    
    Does not truncate the reply; only flags violations.
    """
    count = reply_text.count("?")
    if max_q >= 0 and count > max_q:
        import logging
        logging.getLogger(__name__).warning(
            "max_questions exceeded: found %d '?' but max allowed is %d",
            count, max_q,
        )
        return {"enforced": False, "count": count, "max": max_q, "violation": True}
    return {"enforced": True, "count": count, "max": max_q, "violation": False}


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
        user_asks_review = any(w in msg for w in [
            "复习", "复盘", "回顾", "提醒", "那个事", "之前",
            "继续", "接着说", "说说", "回到刚才", "刚才那个",
            "论文那个", "作业那个", "你刚才说的", "我们接着", "继续刚才",
        ])
        user_mentions_related = target_id and any(
            kw in msg for kw in ["考试", "ddl", "论文", "工作", "压力", "复习", "准备"]
        )
        
        # If user asks review but target_id is empty, try to match from background threads
        if user_asks_review and not target_id:
            sid = getattr(state, "session_id", "")
            session = getattr(thread_manager, "_sessions", {}).get(sid or thread_manager._default_session)
            if session:
                for thread in session.background_threads:
                    if thread.thread_type == "light_chat":
                        continue
                    thread_keywords = thread.name + " " + thread.thread_type + " " + thread.resume_tokens
                    if any(kw in thread_keywords and kw in msg for kw in ["论文", "考试", "ddl", "工作", "复习"]):
                        target_id = thread.id
                        break
        
        if user_asks_review and target_id:
            # 用户明确要求复盘，可以 active
            policy.pull_mode = "active"
            policy.pull_main_thread = True
            policy.goal = "resume_main_thread"
            policy.reason = f"用户主动要求复盘主线: {target_id}"
            policy.max_questions = 0
            policy.allow_humor = False
            policy.response_length = "medium"
            policy.context_profile = "thread_resume"
            return self._finalize_policy(policy)
        elif pull_mode == "soft" and (user_asks_review or user_mentions_related):
            policy.pull_mode = "soft"
            policy.goal = "resume_main_thread"
            policy.reason = f"用户提及相关线索，轻提醒后台主线: {target_id}"
            policy.max_questions = 0
            policy.allow_humor = False
            policy.response_length = "short"
            policy.context_profile = "standard"
            # soft 模式下不正式切换前台主线，只在回复中轻提一句
            policy.pull_main_thread = False
            return self._finalize_policy(policy)
        
        # === 2. 根据意图和状态决定策略 ===
        
        # 安全风险 -> stabilize (最高优先级)
        if intent.primary_intent == "safety":
            policy.goal = "stabilize"
            policy.target_state = "support_crisis"
            policy.allow_advice = False
            policy.allow_humor = False
            policy.max_questions = 0
            policy.max_actions = 0
            policy.response_length = "short"
            policy.context_profile = "minimal"
            policy.skill_verbosity = "none"
            policy.reason = "用户表达安全风险信号，优先稳定"
            return self._finalize_policy(policy)
        
        # 极短问候 -> 简短回应，不反问
        if intent.primary_intent == "casual":
            policy.goal = "stay_light"
            policy.target_state = "light_chat"
            policy.allow_advice = False
            policy.max_questions = 0
            policy.response_length = "short"
            policy.context_profile = "minimal"
            policy.skill_verbosity = "hint"
            policy.reason = "简短问候"
            return self._finalize_policy(policy)
        
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
            return self._finalize_policy(policy)
        
        # 用户想安静 -> quiet (必须优先于其他中等情绪判断)
        if intent.primary_intent == "quiet" or "不想说" in msg or "别问了" in msg:
            policy.goal = "stay_light"
            policy.target_state = "quiet"
            policy.allow_advice = False
            policy.max_questions = 0
            policy.max_actions = 0
            policy.response_length = "short"
            policy.context_profile = "minimal"
            policy.skill_verbosity = "none"
            policy.reason = "用户想安静，留空间"
            return self._finalize_policy(policy)
        
        # 情绪发泄 -> 先接住，不给建议
        if intent.primary_intent == "vent":
            policy.goal = "stabilize"
            policy.target_state = "support_soft"
            policy.allow_advice = False
            policy.allow_humor = False
            policy.max_questions = 0
            policy.response_length = "short"
            policy.context_profile = "standard"
            # 学习类吐槽给短提示+micro action，其他给hint
            if intent.task_category == "study":
                policy.skill_verbosity = "short"
                policy.allow_micro_action = True
            else:
                policy.skill_verbosity = "hint"
            policy.reason = "用户在发泄情绪，先接住"
            return self._finalize_policy(policy)
        
        # 中等情绪 + 可推动 -> push_one_step
        if intent.emotional_intensity > 0.4 and intent.emotional_intensity <= 0.7:
            if intent.action_receptivity > 0.5:
                policy.goal = "push_one_step"
                policy.target_state = "pushable_low_energy"
                policy.allow_advice = True
                policy.max_questions = 1
                policy.max_actions = 1
                policy.response_length = "medium"
                policy.context_profile = "standard"
                policy.skill_verbosity = "short"
            policy.skill_verbosity = "short"
            policy.reason = "用户情绪中等，有一定承接力，可轻推一步"
            return self._finalize_policy(policy)
        # 明确任务 + 紧急 -> task_execution
        if intent.primary_intent == "execute" and intent.task_urgency > 0.6:
            policy.goal = "push_one_step"
            policy.target_state = "task_execution"
            policy.allow_advice = True
            policy.max_questions = 1
            policy.tool_calls = [intent.task_category] if intent.task_category != "none" else []
            policy.response_length = "medium"
            policy.context_profile = "task_heavy"
            policy.skill_verbosity = "card" if intent.action_receptivity > 0.7 else "short"
            policy.reason = f"用户明确执行任务，紧急度{intent.task_urgency:.1f}"
            return self._finalize_policy(policy)
        
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
            return self._finalize_policy(policy)
        
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
            policy.skill_verbosity = "hint"
            policy.reason = "检测到高压话题切换，需要确认紧急度"
            return self._finalize_policy(policy)
        # 闲聊/犯贱 -> stay_light
        if intent.conversation_rhythm in ("bantering", "chill", "sharing"):
            policy.goal = "stay_light"
            policy.target_state = "light_chat"
            policy.allow_humor = self._rel_get(relationship_profile, "humor_mode", "light") != "off"
            policy.allow_advice = False
            policy.max_questions = 1
            policy.response_length = "short"
            policy.context_profile = "standard"
            policy.skill_verbosity = "hint"
            policy.reason = "轻松闲聊模式"
            return self._finalize_policy(policy)
        
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
            return self._finalize_policy(policy)
        
        # 规划 -> planning
        if intent.conversation_rhythm == "planning" or intent.primary_intent == "advice":
            policy.goal = "push_one_step"
            policy.target_state = "planning"
            policy.allow_advice = True
            policy.max_questions = 2
            policy.max_actions = 1
            policy.response_length = "medium"
            policy.context_profile = "task_heavy"
            # 根据任务类别设置 skill_verbosity 和 micro-action/direct-pick
            if intent.task_category == "food":
                policy.skill_verbosity = "hint"
                policy.response_length = "short"
                policy.allow_direct_pick = True
                policy.allow_advice = False  # food: direct pick is not advice
            elif intent.task_category == "social":
                policy.skill_verbosity = "hint"
                policy.response_length = "short"
            elif intent.task_category == "study":
                policy.skill_verbosity = "short"
            else:
                policy.skill_verbosity = "card" if intent.action_receptivity > 0.6 else "short"
            policy.reason = "用户在做规划"
            return self._finalize_policy(policy)
        
        # 默认
        policy.goal = "stay_light"
        policy.target_state = "light_chat"
        policy.context_profile = "standard"
        policy.reason = "默认策略"
        return self._finalize_policy(policy)
    
    def _finalize_policy(self, policy: TurnPolicy) -> TurnPolicy:
        """Apply hard constraints and enforce pull_mode consistency before returning."""
        # Enforce silent pull_mode: no thread reference in reply hint
        if policy.pull_mode == "silent":
            policy.pull_main_thread = False
            policy.hard_constraints.append("no_thread_pull_unless_soft_or_active")
        
        if policy.goal == "stabilize":
            policy.hard_constraints.append("no_numbered_lists_when_stabilize")
        
        if policy.goal == "stay_light":
            policy.hard_constraints.append("no_hotline_when_stay_light")
        
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
