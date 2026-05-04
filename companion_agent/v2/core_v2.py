"""
Core v2 - 本科生陪伴 Agent v2 核心编排器（状态机版）

新流程（信号提取器 -> 状态机 -> 主线管理 -> 策略规划 -> 上下文装配 -> 生成 -> 评审）：
1. IntentEngine - LLM意图理解（信号提取器）
2. StateTracker - 显式状态机
3. ThreadManager - 前台/后台主线管理
4. PolicyPlanner - 策略规划器（替代 DualBrainRouter）
5. ContextAssembler - 渐进式上下文装配
6. ToolRegistry - 工具注册与执行
7. PersonaV2 - 带示例对话的角色
8. LifeSkillsEngine - 本科生生活能力包
9. ResponseJudge - 回复后评审
10. RelationshipMemory - 关系感数据层
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from .intent_engine import IntentEngine, IntentAnalysis
from .state_tracker import StateTracker, ConversationState
from .thread_manager import ThreadManager
from .policy_planner import PolicyPlanner, TurnPolicy
from .context_assembler import ContextAssembler, ContextBlock
from .tool_contract import ToolRegistry, ToolResult, get_tool_registry
from .persona_v2 import PersonaV2, CharacterStyle
from .life_skills import LifeSkillsEngine, LifeAdvice
from .response_judge import ResponseJudge, JudgeResult
from .relationship_memory import RelationshipMemory, RelationshipProfile
from .review_store import ReviewStore
from .review_extractor import (
    ReviewExtractor,
    ReviewSummary,
    ConversationTurn,
    ThreadSnapshot,
)

# 兼容旧版组件
from ..persona import SystemPersonaLayer
from ..memory_adapter import MemoryLayerAdapter, TieredMemoryContext
from ..memory_policy import MemoryUpdatePolicy, MemoryDecision


@dataclass
class CompanionResultV2:
    """v2 处理结果。"""
    reply: str
    
    # 策略
    policy: TurnPolicy
    
    # 意图分析
    intent: IntentAnalysis
    
    # 对话状态
    conversation_state: ConversationState
    
    # 主线
    active_thread: dict[str, Any]
    background_threads: list[dict[str, Any]]
    
    # 记忆
    memory_decision: MemoryDecision
    memory_context: TieredMemoryContext
    memory_updated: bool
    
    # 工具结果
    tool_results: list[ToolResult]
    
    # 评审
    judge_result: JudgeResult | None
    
    # 复盘摘要（仅当 goal 为 review_* 时有值）
    review_summary: ReviewSummary | None = None
    
    # 安全
    safety_flag: bool = False
    
    # 系统提示词
    system_prompt: str = ""
    
    # 调试信息
    debug_info: dict[str, Any] = field(default_factory=dict)


class CompanionAgentCoreV2:
    """v2 核心编排器（状态机版）。"""
    
    def __init__(
        self,
        memory_engine: Any,
        persona_config: Any | None = None,
        character_style: CharacterStyle | None = None,
        enable_judge: bool = True,
        session_id: str = "",
        user_id: str = "",
    ):
        """初始化 v2 核心。
        
        Args:
            memory_engine: 现有的记忆引擎
            persona_config: 兼容旧版角色配置
            character_style: v2角色风格
            enable_judge: 是否启用回复评审
            session_id: 会话ID，用于关系记忆隔离
            user_id: 用户ID，用于关系记忆持久化
        """
        from .llm_runtime import get_llm_runtime
        self._llm_runtime = get_llm_runtime()
        
        # 会话标识
        self.session_id = session_id or "default"
        self.user_id = user_id or "anonymous"
        
        # v2 新组件（统一 Runtime）
        self.intent_engine = IntentEngine(runtime=self._llm_runtime)
        self.state_tracker = StateTracker()
        self.thread_manager = ThreadManager()
        self.policy_planner = PolicyPlanner()
        self.context_assembler = ContextAssembler()
        self.persona_v2 = PersonaV2(style=character_style)
        self.life_skills = LifeSkillsEngine()
        self.response_judge = ResponseJudge(runtime=self._llm_runtime) if enable_judge else None
        self.relationship_memory = RelationshipMemory()
        self.tool_registry = get_tool_registry()
        
        # 复盘存储层
        self.review_store = ReviewStore()
        self.review_extractor = ReviewExtractor()
        
        # 加载持久化的关系档案
        self._load_relationship_memory()
        
        # 兼容旧版
        self.memory = MemoryLayerAdapter(memory_engine)
        self.memory_policy = MemoryUpdatePolicy()
        
        # 旧版 persona 层（用于基础安全规则等）
        self.persona_legacy = SystemPersonaLayer(config=persona_config)
        
        # 记忆写入规则：编排层只负责决策，不直接写入
        # 写入由调用方（server.py）统一提交
        self._pending_memory_store: str | None = None
        
        # 上一轮意图（用于话题切换检测）
        self._previous_intent: IntentAnalysis | None = None
    
    async def generate_reply(
        self,
        user_message: str,
        conversation_history: list[dict[str, str]] | None = None,
        character_card_prompt: str = "",
        memory_enabled: bool = True,
        session_id: str = "",
        user_id: str = "",
    ) -> CompanionResultV2:
        """生成回复（新主入口）。
        
        完整流程：
        1. 意图分析（信号提取）
        2. 主线管理（检测切换/创建/恢复）
        3. 状态更新（显式状态机转移）
        4. 策略规划（TurnPolicy）
        5. 记忆检索
        6. 工具执行（如果需要）
        7. 上下文装配（渐进式）
        8. LLM生成回复
        9. 回复评审
        10. 关系学习
        """
        history = conversation_history or []
        stage_timings: dict[str, float] = {}
        t0 = time.perf_counter()
        
        # === Step 1: 意图分析（信号提取器）===
        t = time.perf_counter()
        sid = session_id or self.session_id
        current_state_summary = self.state_tracker.get_state_summary(sid)
        intent = await self.intent_engine.analyze(
            user_message=user_message,
            conversation_history=history,
            current_state=current_state_summary,
        )
        stage_timings["intent"] = time.perf_counter() - t
        
        # === Step 2: 主线管理 ===
        # 检测话题切换
        is_shift, new_topic = self.thread_manager.detect_topic_shift(
            current_intent=intent,
            previous_intent=self._previous_intent,
        )
        
        if is_shift and new_topic:
            # 创建新主线或切换到已有主线
            thread_metadata = self._build_thread_metadata(intent, user_message)
            if intent.pressure_signal > 0.5:
                self.thread_manager.create_thread(
                    name=new_topic,
                    thread_type="pressure" if intent.pressure_signal > 0.7 else new_topic,
                    urgency_score=intent.task_urgency,
                    emotion_score=intent.emotional_intensity,
                    resume_tokens=user_message[:100],
                    metadata=thread_metadata,
                    session_id=sid,
                )
            else:
                self.thread_manager.create_thread(
                    name=new_topic,
                    thread_type=new_topic,
                    urgency_score=intent.task_urgency,
                    emotion_score=intent.emotional_intensity,
                    resume_tokens=user_message[:100],
                    metadata=thread_metadata,
                    session_id=sid,
                )
        
        # 更新前台主线分数
        if self.thread_manager.get_active_thread_summary(sid):
            self.thread_manager.update_thread(
                thread_id=self.thread_manager.get_active_thread_summary(sid).get("id", ""),
                emotion_score=intent.emotional_intensity,
                user_focus_score=1.0 if intent.topic_shift_type == "none" else 0.5,
                resume_tokens=user_message[:100],
                metadata=self._build_thread_metadata(intent, user_message),
                session_id=sid,
            )
        
        # 如果没有前台主线，创建一个 light_chat
        if not self.thread_manager.get_active_thread_summary(sid):
            self.thread_manager.create_thread(
                name="闲聊",
                thread_type="light_chat",
                urgency_score=0.2,
                emotion_score=intent.emotional_intensity,
                resume_tokens=user_message[:100],
                metadata=self._build_thread_metadata(intent, user_message),
                session_id=sid,
            )
        
        # === Step 3: 状态更新（显式状态机）===
        t = time.perf_counter()
        conv_state = self.state_tracker.update(
            intent_analysis=intent,
            user_message=user_message,
            assistant_reply="",  # 将在生成后更新
            session_id=sid,
        )
        stage_timings["state"] = time.perf_counter() - t
        
        # === Step 4: 策略规划 ===
        relationship_profile = self.relationship_memory.get_profile(session_id=sid)
        policy = self.policy_planner.plan(
            intent=intent,
            state=conv_state,
            thread_manager=self.thread_manager,
            relationship_profile=relationship_profile,
            user_message=user_message,
        )
        
        # 如果需要拉回主线
        if policy.pull_main_thread and policy.main_thread_id:
            self.thread_manager.switch_to_thread(policy.main_thread_id, sid)
        
        # === Step 5: 记忆检索 ===
        t = time.perf_counter()
        memory_context = TieredMemoryContext()
        if memory_enabled:
            memory_tiers = self._decide_memory_tiers(intent)
            memory_context = await self.memory.retrieve_tiered(
                query=user_message,
                situation=intent.task_category if intent.task_category != "none" else "casual_chat",
            )
        stage_timings["memory"] = time.perf_counter() - t

        review_context_text = self._build_review_context(policy=policy, session_id=sid)
        
        # === Step 6: 工具执行 ===
        tool_results: list[ToolResult] = []
        task_context = ""
        
        if policy.tool_calls:
            for tool_name in policy.tool_calls:
                result = await self._execute_tool(
                    tool_name=tool_name,
                    intent=intent,
                    user_message=user_message,
                    memory_context=memory_context,
                )
                if result:
                    tool_results.append(result)
                    if result.user_visible_summary:
                        task_context += f"\n{result.user_visible_summary}"
        
        # 生活技能作为 reasoning tool 执行
        if policy.goal in ("push_one_step", "task_execution") and intent.task_category != "none":
            life_advice = await self.life_skills.execute(
                task_category=intent.task_category,
                user_message=user_message,
                context={
                    "preferences": self._extract_preferences(memory_context),
                    "mood": intent.emotional_state,
                    "time_of_day": self._infer_time_of_day(),
                },
            )
            if life_advice:
                task_context += f"\n【生活建议】{life_advice.advice}"
                active_thread = self.thread_manager.get_active_thread_summary(sid)
                if active_thread:
                    self.thread_manager.update_thread(
                        thread_id=active_thread.get("id", ""),
                        metadata=self._build_thread_metadata(intent, user_message, next_action=life_advice.advice),
                        session_id=sid,
                    )
        
        # === Step 7: 上下文装配 ===
        active_thread_summary = self.thread_manager.get_active_thread_summary(sid)
        background_summaries = self.thread_manager.get_background_summaries(sid)
        
        # 构建角色提示词
        humor_mode = self.relationship_memory.get_humor_mode(
            emotional_intensity=intent.emotional_intensity,
            conversation_mode=conv_state.mode,
            session_id=sid,
        )
        persona_prompt = self.persona_v2.build_system_prompt(
            character_card_prompt=character_card_prompt,
            memory_profile=self.memory.get_profile_summary() if memory_context else {},
            mode=policy.goal,
            scene_hint=intent.emotional_state if policy.goal in ("stabilize", "stay_light") else intent.task_category,
            humor_mode=humor_mode,
        )
        
        # 获取记忆文本
        memory_text = memory_context.to_prompt_section() if memory_context else ""
        if review_context_text:
            memory_text = "\n\n".join(part for part in [memory_text, review_context_text] if part)
        
        # 装配上下文块
        assembly_state = policy.target_state or conv_state.current_state
        context_blocks = self.context_assembler.assemble(
            state=assembly_state,
            policy=policy,
            persona=persona_prompt,
            relationship=self.relationship_memory.get_summary(session_id=sid),
            active_thread=active_thread_summary,
            background_threads=background_summaries,
            memory_context=memory_text,
            task_context=task_context,
            tool_results=[r.user_visible_summary for r in tool_results],
        )
        
        # 构建 LLM 消息
        messages = self.context_assembler.build_messages(
            blocks=context_blocks,
            history=history,
            user_message=user_message,
            max_tokens=self.context_assembler.budget_for_policy(policy),
        )
        
        # === Step 8: LLM生成回复 ===
        t = time.perf_counter()
        assistant_reply = await self._llm_runtime.call("chat", messages)
        assistant_reply = self._sanitize_reply(assistant_reply)
        stage_timings["llm"] = time.perf_counter() - t
        
        # === Step 9: 回复评审 ===
        t = time.perf_counter()
        judge_result = None
        if self.response_judge and self._should_run_judge(
            policy=policy,
            intent=intent,
            user_message=user_message,
            tool_results=tool_results,
        ):
            judge_result = await self.response_judge.judge(
                user_message=user_message,
                assistant_reply=assistant_reply,
                conversation_mode=policy.goal,
                conversation_state=self.state_tracker.get_state_summary(sid),
            )
            if judge_result and not judge_result.is_good and judge_result.improved_reply:
                assistant_reply = judge_result.improved_reply
        stage_timings["judge"] = time.perf_counter() - t
        
        # === Step 10: 关系学习 ===
        old_profile_summary = self.relationship_memory.get_summary(session_id=sid)
        self.relationship_memory.learn_from_interaction(
            user_message=user_message,
            assistant_reply=assistant_reply,
            intent=intent,
            session_id=sid,
        )
        new_profile_summary = self.relationship_memory.get_summary(session_id=sid)
        profile_changed = old_profile_summary != new_profile_summary
        
        # 持久化关系记忆
        self._save_relationship_memory()
        
        # 更新状态中的 assistant_reply
        self.state_tracker.update(
            intent_analysis=intent,
            user_message=user_message,
            assistant_reply=assistant_reply,
            session_id=sid,
        )
        
        # 保存本轮意图
        self._previous_intent = intent
        
        # 记忆更新策略（只决策，不写入）
        t = time.perf_counter()
        memory_decision = MemoryDecision(
            action="ignore",
            reason="记忆已禁用或未触发",
            confidence=0.0,
            requires_confirmation=False,
            privacy_level="public",
            suggested_tags=[],
        )

        if memory_enabled:
            snapshot = self._get_memory_snapshot()
            memory_decision = await self.memory_policy.evaluate(
                user_message=user_message,
                current_memory_snapshot=snapshot,
                situation=intent.task_category,
            )
            if memory_decision.action in ("add", "update") and not memory_decision.requires_confirmation:
                self._pending_memory_store = user_message
        stage_timings["memory_policy"] = time.perf_counter() - t

        # 安全检测
        safety_flag = self._check_safety(user_message, intent)
        
        stage_timings["total"] = time.perf_counter() - t0
        # === Step 10b: 复盘摘要生成（当 goal 为 review_* 时）===
        review_summary = None
        if policy.goal.startswith("review_"):
            review_summary = self._generate_review_summary(
                policy=policy,
                intent=intent,
                state=conv_state,
                history=history,
                user_message=user_message,
                assistant_reply=assistant_reply,
                sid=sid,
            )
            self._finalize_review_summary(review_summary=review_summary, session_id=sid)
        
        # 构建系统提示词摘要（调试用）
        system_prompt = "\n\n".join([b.content for b in context_blocks])
        
        return CompanionResultV2(
            reply=assistant_reply,
            policy=policy,
            intent=intent,
            conversation_state=conv_state,
            active_thread=active_thread_summary,
            background_threads=background_summaries,
            memory_decision=memory_decision,
            memory_context=memory_context,
            memory_updated=False,
            tool_results=tool_results,
            judge_result=judge_result,
            review_summary=review_summary,
            safety_flag=safety_flag,
            system_prompt=system_prompt[:500] + "..." if len(system_prompt) > 500 else system_prompt,
            debug_info={
                "intent": {
                    "primary": intent.primary_intent,
                    "emotion": intent.emotional_state,
                    "rhythm": intent.conversation_rhythm,
                    "task": intent.task_category,
                    "action_receptivity": intent.action_receptivity,
                    "topic_shift": intent.topic_shift_type,
                    "pressure": intent.pressure_signal,
                },
                "state": {
                    "current_state": conv_state.current_state,
                    "assembly_state": assembly_state,
                    "previous_state": conv_state.previous_state,
                    "mode": conv_state.mode,
                    "intimacy": round(conv_state.intimacy_level, 2),
                },
                "policy": {
                    "goal": policy.goal,
                    "pull_main_thread": policy.pull_main_thread,
                    "allow_humor": policy.allow_humor,
                    "allow_advice": policy.allow_advice,
                },
                "threads": {
                    "active": self.thread_manager.get_active_thread_summary(sid),
                    "background_count": len(self.thread_manager.get_background_summaries(sid)),
                },
                "relationship": {
                    "profile_changed": profile_changed,
                    "before": old_profile_summary,
                    "after": new_profile_summary,
                    "session_id": sid,
                },
                "stage_timings": {k: round(v, 3) for k, v in stage_timings.items()},
            },
        )
    
    # === 向后兼容的旧接口 ===
    
    async def process_message(
        self,
        user_message: str,
        conversation_history: list[dict[str, str]] | None = None,
        character_card_prompt: str = "",
        memory_enabled: bool = True,
        session_id: str = "",
        user_id: str = "",
    ) -> CompanionResultV2:
        """处理用户消息（向后兼容，调用新流程）。"""
        return await self.generate_reply(
            user_message=user_message,
            conversation_history=conversation_history,
            character_card_prompt=character_card_prompt,
            memory_enabled=memory_enabled,
            session_id=session_id,
            user_id=user_id,
        )
    
    async def judge_response(
        self,
        user_message: str,
        assistant_reply: str,
        result: CompanionResultV2,
        session_id: str = "",
    ) -> JudgeResult:
        """对生成的回复进行评审（向后兼容）。"""
        if not self.response_judge:
            return JudgeResult(
                is_good=True,
                score=7.0,
                issues=[],
                suggestions=[],
                improved_reply=assistant_reply,
            )
        
        return await self.response_judge.judge(
            user_message=user_message,
            assistant_reply=assistant_reply,
            conversation_mode=result.policy.goal,
            conversation_state=self.state_tracker.get_state_summary(session_id or self.session_id),
        )
    
    async def learn_from_interaction(
        self,
        user_message: str,
        assistant_reply: str,
        intent: IntentAnalysis,
        session_id: str = "",
    ) -> None:
        """从交互中学习关系偏好（向后兼容，现在已在 generate_reply 中自动调用）。"""
        self.relationship_memory.learn_from_interaction(
            user_message=user_message,
            assistant_reply=assistant_reply,
            intent=intent,
            session_id=session_id,
        )
    
    def build_messages_for_llm(
        self,
        result: CompanionResultV2,
        user_message: str,
        history: list[dict[str, str]],
    ) -> list[dict[str, str]]:
        """构建 LLM 消息列表（向后兼容，现在内部已自动装配）。"""
        # 简单返回 system + history + user
        messages = []
        if result.system_prompt:
            messages.append({"role": "system", "content": result.system_prompt})
        messages.extend(history[-6:])  # Reduced for speed
        messages.append({"role": "user", "content": user_message})
        return messages

    async def generate_reply_streaming(
        self,
        user_message: str,
        conversation_history: list[dict[str, str]] | None = None,
        character_card_prompt: str = "",
        memory_enabled: bool = True,
        session_id: str = "",
        user_id: str = "",
    ):
        """流式生成回复。

        Yields:
            {"type": "delta", "delta": str}: 文本片段
            {"type": "final", "result": CompanionResultV2}: 最终结果
        """
        # 复用 generate_reply 的前 7 步逻辑
        history = conversation_history or []
        sid = session_id or self.session_id
        stage_timings: dict[str, float] = {}
        t0 = time.perf_counter()

        # === Steps 1-7: 意图分析、主线管理、状态更新、策略规划、记忆检索、工具执行、上下文装配 ===
        t = time.perf_counter()
        current_state_summary = self.state_tracker.get_state_summary(sid)
        intent = await self.intent_engine.analyze(
            user_message=user_message,
            conversation_history=history,
            current_state=current_state_summary,
        )
        stage_timings["intent"] = time.perf_counter() - t

        is_shift, new_topic = self.thread_manager.detect_topic_shift(
            current_intent=intent,
            previous_intent=self._previous_intent,
        )

        if is_shift and new_topic:
            self.thread_manager.create_thread(
                name=new_topic,
                thread_type="pressure" if intent.pressure_signal > 0.7 else new_topic,
                urgency_score=intent.task_urgency,
                emotion_score=intent.emotional_intensity,
                resume_tokens=user_message[:100],
                metadata=self._build_thread_metadata(intent, user_message),
                session_id=sid,
            )

        if self.thread_manager.get_active_thread_summary(sid):
            self.thread_manager.update_thread(
                thread_id=self.thread_manager.get_active_thread_summary(sid).get("id", ""),
                emotion_score=intent.emotional_intensity,
                user_focus_score=1.0 if intent.topic_shift_type == "none" else 0.5,
                resume_tokens=user_message[:100],
                metadata=self._build_thread_metadata(intent, user_message),
                session_id=sid,
            )

        if not self.thread_manager.get_active_thread_summary(sid):
            self.thread_manager.create_thread(
                name="闲聊",
                thread_type="light_chat",
                urgency_score=0.2,
                emotion_score=intent.emotional_intensity,
                resume_tokens=user_message[:100],
                metadata=self._build_thread_metadata(intent, user_message),
                session_id=sid,
            )

        conv_state = self.state_tracker.update(
            intent_analysis=intent,
            user_message=user_message,
            assistant_reply="",
            session_id=sid,
        )
        stage_timings["state"] = time.perf_counter() - t

        t = time.perf_counter()
        relationship_profile = self.relationship_memory.get_profile(session_id=sid)
        policy = self.policy_planner.plan(
            intent=intent,
            state=conv_state,
            thread_manager=self.thread_manager,
            relationship_profile=relationship_profile,
            user_message=user_message,
        )

        if policy.pull_main_thread and policy.main_thread_id:
            self.thread_manager.switch_to_thread(policy.main_thread_id, sid)

        t = time.perf_counter()
        memory_context = TieredMemoryContext()
        if memory_enabled:
            memory_context = await self.memory.retrieve_tiered(
                query=user_message,
                situation=intent.task_category if intent.task_category != "none" else "casual_chat",
            )
        stage_timings["memory"] = time.perf_counter() - t

        review_context_text = self._build_review_context(policy=policy, session_id=sid)

        tool_results: list[ToolResult] = []
        task_context = ""

        if policy.tool_calls:
            for tool_name in policy.tool_calls:
                result = await self._execute_tool(
                    tool_name=tool_name,
                    intent=intent,
                    user_message=user_message,
                    memory_context=memory_context,
                )
                if result:
                    tool_results.append(result)
                    if result.user_visible_summary:
                        task_context += f"\n{result.user_visible_summary}"

        if policy.goal in ("push_one_step", "task_execution") and intent.task_category != "none":
            life_advice = await self.life_skills.execute(
                task_category=intent.task_category,
                user_message=user_message,
                context={
                    "preferences": self._extract_preferences(memory_context),
                    "mood": intent.emotional_state,
                    "time_of_day": self._infer_time_of_day(),
                },
            )
            if life_advice:
                task_context += f"\n【生活建议】{life_advice.advice}"
                active_thread = self.thread_manager.get_active_thread_summary(sid)
                if active_thread:
                    self.thread_manager.update_thread(
                        thread_id=active_thread.get("id", ""),
                        metadata=self._build_thread_metadata(intent, user_message, next_action=life_advice.advice),
                        session_id=sid,
                    )

        active_thread_summary = self.thread_manager.get_active_thread_summary(sid)
        background_summaries = self.thread_manager.get_background_summaries(sid)

        humor_mode = self.relationship_memory.get_humor_mode(
            emotional_intensity=intent.emotional_intensity,
            conversation_mode=conv_state.mode,
            session_id=sid,
        )
        persona_prompt = self.persona_v2.build_system_prompt(
            character_card_prompt=character_card_prompt,
            memory_profile=self.memory.get_profile_summary() if memory_context else {},
            mode=policy.goal,
            scene_hint=intent.emotional_state if policy.goal in ("stabilize", "stay_light") else intent.task_category,
            humor_mode=humor_mode,
        )

        memory_text = memory_context.to_prompt_section() if memory_context else ""
        if review_context_text:
            memory_text = "\n\n".join(part for part in [memory_text, review_context_text] if part)

        assembly_state = policy.target_state or conv_state.current_state
        context_blocks = self.context_assembler.assemble(
            state=assembly_state,
            policy=policy,
            persona=persona_prompt,
            relationship=self.relationship_memory.get_summary(session_id=sid),
            active_thread=active_thread_summary,
            background_threads=background_summaries,
            memory_context=memory_text,
            task_context=task_context,
            tool_results=[r.user_visible_summary for r in tool_results],
        )

        messages = self.context_assembler.build_messages(
            blocks=context_blocks,
            history=history,
            user_message=user_message,
            max_tokens=self.context_assembler.budget_for_policy(policy),
        )

        # === Step 8: 流式 LLM 生成 ===
        t = time.perf_counter()
        assistant_reply = ""
        try:
            async for delta in self._llm_runtime.stream("chat", messages):
                assistant_reply += delta
                yield {"type": "delta", "delta": delta}
        except Exception:
            # 流式失败时回退到非流式
            fallback_reply = await self._llm_runtime.call("chat", messages)
            assistant_reply = fallback_reply
            yield {"type": "delta", "delta": fallback_reply}

        assistant_reply = self._sanitize_reply(assistant_reply)
        stage_timings["llm"] = time.perf_counter() - t

        # === Step 9: 回复评审 ===
        t = time.perf_counter()
        judge_result = None
        if self.response_judge and self._should_run_judge(
            policy=policy,
            intent=intent,
            user_message=user_message,
            tool_results=tool_results,
        ):
            judge_result = await self.response_judge.judge(
                user_message=user_message,
                assistant_reply=assistant_reply,
                conversation_mode=policy.goal,
                conversation_state=self.state_tracker.get_state_summary(sid),
            )
            if judge_result and not judge_result.is_good and judge_result.improved_reply:
                assistant_reply = judge_result.improved_reply
        stage_timings["judge"] = time.perf_counter() - t

        # === Step 10: 关系学习 ===
        old_profile_summary = self.relationship_memory.get_summary(session_id=sid)
        self.relationship_memory.learn_from_interaction(
            user_message=user_message,
            assistant_reply=assistant_reply,
            intent=intent,
            session_id=sid,
        )
        new_profile_summary = self.relationship_memory.get_summary(session_id=sid)
        profile_changed = old_profile_summary != new_profile_summary
        self._save_relationship_memory()

        self.state_tracker.update(
            intent_analysis=intent,
            user_message=user_message,
            assistant_reply=assistant_reply,
            session_id=sid,
        )
        self._previous_intent = intent

        # 记忆更新策略
        t = time.perf_counter()
        memory_decision = MemoryDecision(
            action="ignore",
            reason="记忆已禁用或未触发",
            confidence=0.0,
            requires_confirmation=False,
            privacy_level="public",
            suggested_tags=[],
        )

        if memory_enabled:
            snapshot = self._get_memory_snapshot()
            memory_decision = await self.memory_policy.evaluate(
                user_message=user_message,
                current_memory_snapshot=snapshot,
                situation=intent.task_category,
            )
            if memory_decision.action in ("add", "update") and not memory_decision.requires_confirmation:
                self._pending_memory_store = user_message
        stage_timings["memory_policy"] = time.perf_counter() - t

        safety_flag = self._check_safety(user_message, intent)
        system_prompt = "\n\n".join([b.content for b in context_blocks])
        
        stage_timings["total"] = time.perf_counter() - t0

        review_summary = None
        if policy.goal.startswith("review_"):
            review_summary = self._generate_review_summary(
                policy=policy,
                intent=intent,
                state=conv_state,
                history=history,
                user_message=user_message,
                assistant_reply=assistant_reply,
                sid=sid,
            )
            self._finalize_review_summary(review_summary=review_summary, session_id=sid)

        result = CompanionResultV2(
            reply=assistant_reply,
            policy=policy,
            intent=intent,
            conversation_state=conv_state,
            active_thread=active_thread_summary,
            background_threads=background_summaries,
            memory_decision=memory_decision,
            memory_context=memory_context,
            memory_updated=False,
            tool_results=tool_results,
            judge_result=judge_result,
            review_summary=review_summary,
            safety_flag=safety_flag,
            system_prompt=system_prompt[:500] + "..." if len(system_prompt) > 500 else system_prompt,
            debug_info={
                "intent": {
                    "primary": intent.primary_intent,
                    "emotion": intent.emotional_state,
                    "rhythm": intent.conversation_rhythm,
                    "task": intent.task_category,
                    "action_receptivity": intent.action_receptivity,
                    "topic_shift": intent.topic_shift_type,
                    "pressure": intent.pressure_signal,
                },
                "state": {
                    "current_state": conv_state.current_state,
                    "assembly_state": assembly_state,
                    "previous_state": conv_state.previous_state,
                    "mode": conv_state.mode,
                    "intimacy": round(conv_state.intimacy_level, 2),
                },
                "policy": {
                    "goal": policy.goal,
                    "pull_main_thread": policy.pull_main_thread,
                    "allow_humor": policy.allow_humor,
                    "allow_advice": policy.allow_advice,
                },
                "threads": {
                    "active": self.thread_manager.get_active_thread_summary(sid),
                    "background_count": len(self.thread_manager.get_background_summaries(sid)),
                },
                "relationship": {
                    "profile_changed": profile_changed,
                    "before": old_profile_summary,
                    "after": new_profile_summary,
                    "session_id": sid,
                },
                "stage_timings": {k: round(v, 3) for k, v in stage_timings.items()},
            },
        )

        yield {"type": "final", "result": result}
    
    # === 工具执行 ===
    
    async def _execute_tool(
        self,
        tool_name: str,
        intent: IntentAnalysis,
        user_message: str,
        memory_context: TieredMemoryContext,
    ) -> ToolResult | None:
        """执行工具。"""
        tool = self.tool_registry.get(tool_name)
        if not tool:
            return None
        
        # 伪执行：根据工具类型返回模拟结果
        if tool.tool_type == "reasoning":
            return await self._execute_reasoning_tool(tool_name, intent, user_message)
        elif tool.tool_type == "lookup":
            return await self._execute_lookup_tool(tool_name, intent, user_message)
        elif tool.tool_type == "action":
            return await self._execute_action_tool(tool_name, intent, user_message)
        
        return None
    
    async def _execute_reasoning_tool(
        self,
        tool_name: str,
        intent: IntentAnalysis,
        user_message: str,
    ) -> ToolResult:
        """执行 reasoning 工具（伪执行，返回分析和建议）。"""
        if tool_name == "diet_recommend":
            return ToolResult(
                tool_name=tool_name,
                tool_type="reasoning",
                success=True,
                confidence=0.8,
                result={"recommendation": "根据当前时间和情绪推荐食物"},
                user_visible_summary="【饮食分析】根据你现在的状态，建议吃点轻食或你喜欢的 comfort food。",
            )
        elif tool_name == "study_plan":
            return ToolResult(
                tool_name=tool_name,
                tool_type="reasoning",
                success=True,
                confidence=0.7,
                result={"sorted_tasks": ["task1", "task2"]},
                user_visible_summary="【学习规划】已帮你排序任务，建议先处理最紧急的那件。",
            )
        elif tool_name == "reply_advice":
            return ToolResult(
                tool_name=tool_name,
                tool_type="reasoning",
                success=True,
                confidence=0.6,
                result={"options": ["选项A", "选项B"]},
                user_visible_summary="【回复建议】给你几个回复方向，你可以挑一个顺手的。",
            )
        
        return ToolResult(
            tool_name=tool_name,
            tool_type="reasoning",
            success=False,
            confidence=0.0,
            error="未知 reasoning 工具",
        )
    
    async def _execute_lookup_tool(
        self,
        tool_name: str,
        intent: IntentAnalysis,
        user_message: str,
    ) -> ToolResult:
        """执行 lookup 工具（伪执行）。"""
        return ToolResult(
            tool_name=tool_name,
            tool_type="lookup",
            success=True,
            confidence=0.5,
            result={},
            user_visible_summary=f"【查询结果】已查询 {tool_name} 相关信息。",
        )
    
    async def _execute_action_tool(
        self,
        tool_name: str,
        intent: IntentAnalysis,
        user_message: str,
    ) -> ToolResult:
        """执行 action 工具（伪执行，生成草稿/关键词）。"""
        if tool_name == "order_food":
            return ToolResult(
                tool_name=tool_name,
                tool_type="action",
                success=True,
                confidence=0.9,
                requires_confirmation=True,
                result={"search_keywords": "轻食 外卖", "platform_link": ""},
                user_visible_summary="【外卖草稿】已生成搜索关键词，需要你确认后再下单。",
                follow_up_options=["确认", "换一个", "我自己来"],
            )
        elif tool_name == "schedule_reminder":
            return ToolResult(
                tool_name=tool_name,
                tool_type="action",
                success=True,
                confidence=0.9,
                requires_confirmation=True,
                result={"reminder_set": False},
                user_visible_summary="【提醒草稿】已记录提醒内容，需要你确认时间。",
                follow_up_options=["确认", "改时间", "取消"],
            )
        
        return ToolResult(
            tool_name=tool_name,
            tool_type="action",
            success=False,
            confidence=0.0,
            error="未知 action 工具",
        )
    
    # === 内部方法 ===
    
    def _sanitize_reply(self, text: str) -> str:
        """清理回复文本。"""
        if not text:
            return ""
        # 去除多余的空行
        lines = text.split("\n")
        lines = [line for line in lines if line.strip()]
        return "\n".join(lines)

    def _should_run_judge(
        self,
        policy: TurnPolicy,
        intent: IntentAnalysis,
        user_message: str,
        tool_results: list[ToolResult],
    ) -> bool:
        """轻场景 fast path：不是每轮都跑评审。"""
        # 短寒暄不评审
        if len(user_message.strip()) <= 8:
            return False

        # 普通闲聊/互怼/安静模式不评审
        if intent.primary_intent in {"casual", "banter", "quiet"}:
            return False

        # 情绪支持/安全/建议/有工具结果/长回复才评审
        if intent.primary_intent in {"emotional_support", "safety", "advice"}:
            return True

        # 已有工具结果时评审
        if tool_results:
            return True

        # 轻场景默认跳过
        if policy.goal == "stay_light" and not tool_results:
            if len(user_message) < 80 and intent.emotional_intensity < 0.55:
                return False
        if policy.goal == "resume_main_thread" and len(user_message) < 40 and not tool_results:
            return False
        return True
    
    def _decide_memory_tiers(self, intent: IntentAnalysis) -> list[str]:
        """根据意图决定检索哪些记忆层级。"""
        if intent.emotional_intensity > 0.6:
            return ["profile", "preferences", "episodic_events", "safety_notes"]
        elif intent.task_category in ("food", "study", "campus"):
            return ["profile", "preferences", "long_term_goals"]
        else:
            return ["profile", "preferences"]
    
    def _extract_preferences(self, memory_context: TieredMemoryContext) -> dict[str, Any]:
        """从记忆上下文提取偏好。"""
        return {}
    
    def _infer_time_of_day(self) -> str:
        """推断当前时间段。"""
        import datetime
        hour = datetime.datetime.now().hour
        
        if 5 <= hour < 11:
            return "早餐"
        elif 11 <= hour < 14:
            return "午餐"
        elif 14 <= hour < 17:
            return "下午"
        elif 17 <= hour < 21:
            return "晚餐"
        else:
            return "夜宵"
    
    def _check_safety(self, user_message: str, intent: IntentAnalysis) -> bool:
        """安全检查。"""
        sensitive_keywords = [
            "想死", "自杀", "自残", "伤害", "kill", "suicide", "self-harm",
            "hurt", "abuse", "violence", "crisis", "emergency",
        ]
        
        t = user_message.lower()
        return any(kw in t for kw in sensitive_keywords)

    def _build_review_context(self, policy: TurnPolicy, session_id: str) -> str:
        """为复盘/主线恢复场景注入最近复盘摘要。"""
        sections: list[str] = []

        if policy.goal == "resume_main_thread":
            latest = self.review_store.get_latest_review(session_id)
            if latest:
                summary = latest.system_summary or {}
                actions = summary.get("next_actions", [])[:2]
                blockers = summary.get("blockers", [])[:2]
                sections.append("【最近复盘】")
                sections.append(f"范围：{latest.scope}")
                if summary.get("dominant_emotion"):
                    sections.append(f"主导情绪：{summary['dominant_emotion']}")
                if blockers:
                    sections.append(f"最近卡点：{'；'.join(blockers)}")
                if actions:
                    sections.append(f"上次留下的下一步：{'；'.join(actions)}")

        if policy.goal == "review_week":
            from datetime import datetime, timedelta

            today = datetime.now()
            week_start = (today - timedelta(days=today.weekday())).strftime("%Y-%m-%d")
            weekly = self.review_store.get_weekly_summary(session_id, week_start)
            if weekly.get("has_data"):
                sections.append("【本周复盘参考】")
                if weekly.get("dominant_emotion"):
                    sections.append(f"本周主导情绪：{weekly['dominant_emotion']}")
                if weekly.get("top_blockers"):
                    sections.append(f"反复卡点：{'；'.join(weekly['top_blockers'][:3])}")
                if weekly.get("pending_actions"):
                    sections.append(f"待续动作：{'；'.join(weekly['pending_actions'][:2])}")

        return "\n".join(sections)

    def _generate_review_summary(
        self,
        policy: TurnPolicy,
        intent: IntentAnalysis,
        state: ConversationState,
        history: list[dict[str, str]],
        user_message: str,
        assistant_reply: str,
        sid: str,
    ) -> ReviewSummary:
        """生成复盘结构化摘要（用户可见 + 系统内部）。
        
        优先走 ReviewExtractor 的多轮抽取，失败时回退到轻规则摘要。
        """
        scope = policy.goal.replace("review_", "")
        turns = self._build_review_turns(
            history=history,
            user_message=user_message,
            assistant_reply=assistant_reply,
            intent=intent,
        )
        active_snapshot = self._thread_summary_to_snapshot(self.thread_manager.get_active_thread_summary(sid))
        background_snapshots = [
            snapshot
            for snapshot in (
                self._thread_summary_to_snapshot(summary)
                for summary in self.thread_manager.get_background_summaries(sid)
            )
            if snapshot is not None
        ]
        recent_reviews = [
            record.system_summary
            for record in self.review_store.get_reviews(session_id=sid, limit=5)
            if record.system_summary
        ]

        try:
            extracted = self.review_extractor.extract(
                turns=turns,
                active_thread=active_snapshot,
                background_threads=background_snapshots,
                current_state=self.state_tracker.get_state_summary(sid),
                scope=scope,
                recent_reviews=recent_reviews,
            )
            if extracted and extracted.structured:
                if not extracted.user_visible:
                    extracted.user_visible = assistant_reply
                return extracted
        except Exception:
            pass
        
        # 提取关键信息
        active_thread = self.thread_manager.get_active_thread_summary(sid)
        
        # 情绪趋势
        emotion_history = state.emotion_history[-5:] if state.emotion_history else []
        intensities = [e[1] for e in emotion_history]
        avg_intensity = round(sum(intensities) / len(intensities), 2) if intensities else 0.0
        
        # 关键事件（从用户消息中抽取具体活动）
        key_events = []
        # 提取用户消息中的活动描述（过滤掉复盘请求本身）
        user_msg_clean = user_message.strip()
        review_phrases = ["复盘", "梳理", "总结", "回顾", "帮我", "今天", "这周"]
        is_pure_request = any(ph in user_msg_clean for ph in review_phrases) and len(user_msg_clean) < 30
        if not is_pure_request:
            key_events.append(user_msg_clean[:100])
        
        # 补充主线中的事件背景
        if active_thread and active_thread.get("resume_tokens"):
            rt = active_thread.get("resume_tokens", "")
            if rt != user_msg_clean and len(rt) > 5:
                key_events.append(rt[:100])
        
        # 能量模式推断
        energy_pattern = "stable"
        if intensities:
            if intensities[0] > 0.6 and intensities[-1] < 0.4:
                energy_pattern = "前高后低"
            elif intensities[0] < 0.4 and intensities[-1] > 0.6:
                energy_pattern = "前低后高"
            elif max(intensities) - min(intensities) > 0.4:
                energy_pattern = "波动大"
        
        # 卡点/困难（从用户消息中推断）
        blockers = []
        blocker_keywords = [
            "写不完", "被拒", "打回", "效率低", "松懈", "没状态", "焦虑", "累",
            "困难", "压力", "崩溃", "失败", "不顺", "拖延", "逃避", "不想",
            "后悔", "乱", "迷茫", "卡住", "瓶颈", "冲突", "纠结",
        ]
        for kw in blocker_keywords:
            if kw in user_message:
                blockers.append(kw)
        
        # 小成就（从回复中推断积极信号）
        wins = []
        if any(kw in assistant_reply for kw in ["对", "很好", "进步", "完成", "改完", "梳理"]):
            wins.append("主动复盘")
        if intent.action_receptivity > 0.5:
            wins.append("接受建议意愿高")
        
        # 下一步行动（从回复中提取）
        next_actions = []
        if "明天" in assistant_reply or "下次" in assistant_reply or "试试" in assistant_reply:
            # 提取包含行动建议的句子
            for sent in assistant_reply.split("。"):
                if any(kw in sent for kw in ["试试", "可以", "建议", "要不", "定个"]):
                    next_actions.append(sent.strip())
        if not next_actions and policy.goal.startswith("review_"):
            next_actions.append("继续观察" + scope + "节奏")
        
        # 结构化摘要
        structured = {
            "time_range": scope,
            "dominant_emotion": state.dominant_emotion,
            "emotion_trend": state.emotional_trend,
            "avg_intensity": avg_intensity,
            "energy_pattern": energy_pattern,
            "key_events": key_events[:5],
            "blockers": list(set(blockers)),
            "wins": wins,
            "next_actions": next_actions[:3],
            "user_scene": state.user_scene,
            "topics": state.recent_topics[-3:],
        }
        
        return ReviewSummary(
            scope=scope,
            user_visible=assistant_reply,
            structured=structured,
        )

    def _finalize_review_summary(
        self,
        review_summary: ReviewSummary | None,
        session_id: str = "",
    ) -> None:
        """统一处理复盘摘要的线程回写和持久化。"""
        if not review_summary:
            return
        sid = session_id or self.session_id
        self.apply_review_summary_to_threads(review_summary, session_id=sid)
        self.review_store.save_review(
            session_id=sid,
            scope=review_summary.scope,
            user_visible_text=review_summary.user_visible,
            system_summary=review_summary.structured,
        )

    def _build_review_turns(
        self,
        history: list[dict[str, str]],
        user_message: str,
        assistant_reply: str,
        intent: IntentAnalysis,
    ) -> list[ConversationTurn]:
        """把最近对话转换成 ReviewExtractor 可消费的轮次。"""
        turns: list[ConversationTurn] = []
        for msg in history[-6:]:
            turns.append(
                ConversationTurn(
                    role=msg.get("role", "user"),
                    content=msg.get("content", ""),
                    intent={},
                )
            )
        turns.append(
            ConversationTurn(
                role="user",
                content=user_message,
                intent={
                    "emotional_intensity": intent.emotional_intensity,
                    "task_category": intent.task_category,
                    "emotional_state": intent.emotional_state,
                },
            )
        )
        turns.append(ConversationTurn(role="assistant", content=assistant_reply, intent={}))
        return turns

    def _thread_summary_to_snapshot(self, summary: dict[str, Any]) -> ThreadSnapshot | None:
        """把线程摘要转换成复盘抽取器使用的快照结构。"""
        if not summary:
            return None
        return ThreadSnapshot(
            id=summary.get("id", ""),
            name=summary.get("name", ""),
            thread_type=summary.get("type", ""),
            resume_tokens=summary.get("resume_tokens", ""),
            resume_capsule=summary.get("resume_capsule", {}) or {},
            urgency_score=float(summary.get("urgency", 0.0)),
            emotion_score=float(summary.get("emotion", 0.0)),
        )

    def apply_review_summary_to_threads(
        self,
        review_summary: ReviewSummary,
        session_id: str = "",
    ) -> None:
        """把复盘摘要回写到相关线程的 resume_capsule。

        让"总结过的东西下次真能接上"。
        """
        sid = session_id or self.session_id
        structured = review_summary.structured

        # 找到与复盘相关的线程（当前 active 或最近相关的 background）
        active = self.thread_manager.get_active_thread_summary(sid)
        backgrounds = self.thread_manager.get_background_summaries(sid)

        # 构建更新的 capsule 字段
        next_actions = structured.get("next_actions", [])
        blockers = structured.get("blockers", [])
        topics = structured.get("topics", [])
        dominant_emotion = structured.get("dominant_emotion", "")

        # 如果有 active thread，优先更新它
        if active and active.get("id"):
            thread_id = active["id"]
            metadata_update = {
                "current_blocker": ", ".join(blockers) if blockers else active.get("resume_capsule", {}).get("current_blocker", ""),
                "last_progress": review_summary.user_visible[:120] if review_summary.user_visible else "",
                "next_recommended_action": next_actions[0] if next_actions else active.get("resume_capsule", {}).get("next_recommended_action", ""),
                "why_it_matters": active.get("resume_capsule", {}).get("why_it_matters", "") or "这是用户当前在意的一条生活主线。",
                "review_dominant_emotion": dominant_emotion,
                "review_topics": topics,
                "review_next_actions": next_actions,
                "review_blockers": blockers,
                "last_review_scope": review_summary.scope,
                "last_review_at": time.time(),
            }
            self.thread_manager.update_thread(
                thread_id=thread_id,
                metadata=metadata_update,
                session_id=sid,
            )

        # 也更新 background 中相关的线程（按 topic 匹配）
        for bg in backgrounds:
            bg_id = bg.get("id")
            if not bg_id:
                continue
            bg_name = bg.get("name", "")
            # 简单匹配：线程名或类型与复盘 topics 相关
            should_update = False
            for topic in topics:
                if topic.lower() in bg_name.lower() or bg.get("type", "") == topic:
                    should_update = True
                    break
            if should_update:
                self.thread_manager.update_thread(
                    thread_id=bg_id,
                    metadata={
                        "next_recommended_action": next_actions[0] if next_actions else bg.get("resume_capsule", {}).get("next_recommended_action", ""),
                        "last_review_scope": review_summary.scope,
                        "last_review_at": time.time(),
                    },
                    session_id=sid,
                )

    def _build_thread_metadata(
        self,
        intent: IntentAnalysis,
        user_message: str,
        next_action: str = "",
    ) -> dict[str, Any]:
        """为线程恢复胶囊构建可复用的阶段元数据。"""
        stage = intent.task_category if intent.task_category != "none" else intent.primary_intent
        blocker = user_message[:80]
        why = intent.emotional_context or "这是用户当前在意的一条生活主线。"
        return {
            "current_stage": stage,
            "why_it_matters": why[:120],
            "current_blocker": blocker,
            "next_action": next_action[:80] if next_action else "",
        }
    
    def _get_memory_snapshot(self) -> dict[str, Any]:
        """获取记忆快照。"""
        return self.memory._engine.snapshot()
    
    # === 关系记忆持久化 ===
    
    def _get_relationship_memory_path(self) -> str:
        """获取关系记忆文件路径。"""
        import os
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        filename = f"relationship_memory_{self.user_id}.json"
        return os.path.join(base_dir, filename)
    
    def _load_relationship_memory(self) -> None:
        """从磁盘加载关系记忆。"""
        import json
        import os
        
        path = self._get_relationship_memory_path()
        if not os.path.exists(path):
            return
        
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            for session_id, profile_data in data.items():
                profile = RelationshipProfile(
                    comfort_style=profile_data.get("comfort_style", "balanced"),
                    banter_tolerance=profile_data.get("banter_tolerance", 0.5),
                    advice_threshold=profile_data.get("advice_threshold", 0.5),
                    humor_mode=profile_data.get("humor_mode", "light"),
                    version=profile_data.get("version", 0),
                )
                self.relationship_memory._profiles[session_id] = profile
        except Exception:
            pass
    
    def _save_relationship_memory(self) -> None:
        """保存关系记忆到磁盘。"""
        import json
        import os
        
        path = self._get_relationship_memory_path()
        
        data = {}
        for session_id, profile in self.relationship_memory._profiles.items():
            data[session_id] = {
                "comfort_style": profile.comfort_style,
                "banter_tolerance": profile.banter_tolerance,
                "advice_threshold": profile.advice_threshold,
                "humor_mode": profile.humor_mode,
                "version": profile.version,
            }
        
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
    
    async def commit_memory(self) -> bool:
        """提交待写入的记忆（由调用方在生成回复后统一调用）。"""
        if self._pending_memory_store:
            try:
                await self.memory.store("user", self._pending_memory_store)
                self._pending_memory_store = None
                return True
            except Exception:
                return False
        return False
    
    def get_status(self, session_id: str = "") -> dict[str, Any]:
        """获取当前状态。"""
        sid = session_id or self.session_id
        state = self.state_tracker._get_or_create_state(sid)
        return {
            "version": "2.1",
            "persona_name": self.persona_v2.style.name,
            "session_id": sid,
            "user_id": self.user_id,
            "current_state": state.current_state,
            "brain_mode": state.mode,
            "intimacy_level": round(state.intimacy_level, 2),
            "dominant_emotion": state.dominant_emotion,
            "recent_topics": state.recent_topics,
            "active_thread": self.thread_manager.get_active_thread_summary(sid),
            "background_count": len(self.thread_manager.get_background_summaries(sid)),
        }
