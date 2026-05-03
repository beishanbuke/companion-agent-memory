"""Context Engine v3 - 重构版

Companion Runtime Brain Architecture (v2)

核心流程：
1. 双脑模式判断（chat vs task）
2. LLM 意图理解（不是 keyword 匹配）
3. 生活能力调用（如果需要）
4. 示例对话注入（定义角色说话方式）
5. 上下文组装
6. 回复后评审（生成后）

旧流程保留作为降级方案。
"""

from __future__ import annotations

import asyncio
from typing import Any

from .types import ChatMessage, ContextBlock, ContextBuildInput, ContextBuildResult, RouteResult, TokenSummary, TraceStep
from .token_budget import apply_token_budget, estimate_tokens
from .prompt_composer import compose_messages

# 新架构模块
from .companion_mode import decide_companion_mode, ModeDecision
from .llm_router import understand_intent, IntentUnderstanding
from .persona_examples import get_examples_for_prompt, get_tone_guidelines, get_core_persona
from .response_reviewer import review_response, rewrite_response

# 旧模块（降级用）
from .signal_detectors import detect_all_signals
from .state_tracker import get_state_tracker
from .micro_capsules import build_capsules_from_signals
from .skill_manifests import select_skills, get_skill_by_id
from .response_policy import select_response_policy


# 连续模式追踪（简单版，存在内存中）
_mode_history: dict[str, list[str]] = {}


def _get_recent_mode(user_id: str, default: str = "chat") -> str:
    """获取用户最近的模式，保持连续性"""
    history = _mode_history.get(user_id, [])
    return history[-1] if history else default


def _record_mode(user_id: str, mode: str):
    """记录用户当前模式"""
    if user_id not in _mode_history:
        _mode_history[user_id] = []
    _mode_history[user_id].append(mode)
    # 只保留最近 10 轮
    if len(_mode_history[user_id]) > 10:
        _mode_history[user_id] = _mode_history[user_id][-10:]


def _recent_history_text(history: list[ChatMessage], max_turns: int = 6) -> str:
    return "\n".join(f"{m.role}: {m.content}" for m in history[-max_turns:])


def _load_core_blocks_v2(
    character_id: str,
    character_prompt: str = "",
    mode_decision: ModeDecision | None = None,
    intent: IntentUnderstanding | None = None,
) -> list[ContextBlock]:
    """加载核心上下文块（新架构版）"""
    
    # 核心人格（用 persona_examples 的 core_persona）
    core_persona = get_core_persona()
    
    # 语调指导
    tone_guide = get_tone_guidelines()
    
    # 根据模式选择示例
    example_categories = ["casual_chat", "emotional_support", "banter", "refuse_preach"]
    if mode_decision and mode_decision.primary_mode == "task":
        example_categories = ["study", "food", "social", "task_help"]
    elif intent:
        topic_map = {
            "food": ["food"],
            "study": ["study"],
            "social": ["social"],
            "music": ["casual_chat"],
            "emotion": ["emotional_support", "banter"],
            "campus": ["campus"],
        }
        example_categories = topic_map.get(intent.topic_area, ["casual_chat", "emotional_support"])
    
    examples = get_examples_for_prompt(categories=example_categories, limit=8)
    
    # 模式上下文
    mode_context = ""
    if mode_decision:
        mode_context = f"""
【当前模式】{mode_decision.primary_mode}
【用户意图】{mode_decision.user_intent}
【情绪状态】{mode_decision.emotional_state}
【建议语调】{mode_decision.suggested_tone}
"""
    
    # 意图上下文
    intent_context = ""
    if intent:
        intent_context = f"""
【意图理解】
- 用户想要：{intent.intent_description}
- 情绪：{intent.emotional_state}（强度{intent.emotional_intensity}）
- 关系时刻：{intent.relationship_moment}
- 期望回应：{intent.desired_action}
- 话题：{intent.topic_area}
- 隐式状态：{intent.implicit_state}
"""
    
    core_content = f"""{core_persona}

{tone_guide}

{examples}

{mode_context}

{intent_context}

【核心原则】
1. 会接话，不是会回答。先接情绪/语气，再给内容。
2. 允许留白。不是所有话都要接满，有时候"嗯"就够了。
3. 具体 > 抽象。说"二食堂麻辣烫"而不是"吃点好的"。
4. 行动 > 安慰。说"我给你点杯奶茶"而不是"别难过"。
5. 关系感 > 正确性。有时候一起吐槽比给正确建议更有用。
6. 连续性感知。考虑上文，不要每轮从零开始。
"""
    
    blocks = [
        ContextBlock(
            id="system:core_v2",
            type="system",
            role="system",
            title="Core Persona & Examples",
            content=core_content,
            priority=100,
            tokens=estimate_tokens(core_content),
            required=True,
            source="system",
            position="before_history",
        ),
    ]
    
    # 如果有角色卡 prompt，也加入
    if character_prompt and character_prompt.strip():
        blocks.append(
            ContextBlock(
                id=f"persona:{character_id}",
                type="persona",
                role="system",
                title="Character Card",
                content=character_prompt.strip(),
                priority=95,
                tokens=estimate_tokens(character_prompt),
                required=True,
                source="persona",
                position="before_history",
            )
        )
    
    return blocks


async def build_context_v3(input_data: ContextBuildInput) -> ContextBuildResult:
    """构建上下文（新架构）。
    
    Flow:
    1. 双脑模式判断（chat vs task）
    2. LLM 意图理解
    3. 生活能力调用（task mode 时）
    4. 旧信号检测（降级/补充）
    5. 上下文组装
    """
    trace: list[TraceStep] = []
    
    # === Step 1: 双脑模式判断 ===
    recent_mode = _get_recent_mode(input_data.user_id)
    
    try:
        mode_decision = await decide_companion_mode(
            user_message=input_data.user_message,
            chat_history=[m.to_dict() for m in input_data.history[-5:]],
            recent_mode=recent_mode,
        )
    except Exception as e:
        trace.append(TraceStep(step="Mode Decision", detail=f"LLM failed, fallback: {e}"))
        mode_decision = ModeDecision(
            primary_mode="chat",
            confidence=0.5,
            user_intent="日常交流",
            emotional_state="neutral",
            suggested_tone="natural",
        )
    
    _record_mode(input_data.user_id, mode_decision.primary_mode)
    
    trace.append(TraceStep(
        step="Companion Mode",
        detail=f"Mode: {mode_decision.primary_mode}, confidence: {mode_decision.confidence:.2f}",
        data={
            "mode": mode_decision.primary_mode,
            "confidence": mode_decision.confidence,
            "intent": mode_decision.user_intent,
            "emotional_state": mode_decision.emotional_state,
            "tone": mode_decision.suggested_tone,
        },
    ))
    
    # === Step 2: LLM 意图理解 ===
    try:
        # 从记忆中提取相关片段
        memory_snippets: list[str] = []
        # 如果有历史，简单提取用户提到的话题
        for msg in input_data.history[-10:]:
            if msg.role == "user" and len(msg.content) > 5:
                memory_snippets.append(msg.content[:50])
        
        intent = await understand_intent(
            user_message=input_data.user_message,
            chat_history=[m.to_dict() for m in input_data.history[-5:]],
            memory_snippets=memory_snippets,
        )
    except Exception as e:
        trace.append(TraceStep(step="Intent Understanding", detail=f"LLM failed, fallback: {e}"))
        intent = IntentUnderstanding(
            intent_description="日常交流",
            emotional_state="neutral",
            emotional_intensity=0.5,
            relationship_moment="普通对话",
            desired_action="自然回应",
            topic_area="others",
            implicit_state="随口一提",
            confidence=0.4,
        )
    
    trace.append(TraceStep(
        step="Intent Understanding",
        detail=f"Intent: {intent.intent_description}, topic: {intent.topic_area}",
        data={
            "intent": intent.intent_description,
            "emotional_state": intent.emotional_state,
            "intensity": intent.emotional_intensity,
            "relationship_moment": intent.relationship_moment,
            "desired_action": intent.desired_action,
            "topic": intent.topic_area,
            "implicit_state": intent.implicit_state,
        },
    ))
    
    # === Step 3: 旧信号检测（降级用 + MCP 工具触发）===
    signals = detect_all_signals(input_data.user_message)
    
    def _is_active(v):
        if isinstance(v, list):
            return any(s.active for s in v)
        return v.active
    
    active_signals = {k: v for k, v in signals.items() if _is_active(v)}
    
    # === Step 4: 生活能力调用（Task Mode）===
    life_advice = None
    if mode_decision.primary_mode in ("task", "mixed"):
        try:
            if intent.topic_area == "food":
                from .life_skills import DietAdvisor
                advisor = DietAdvisor()
                life_advice = await advisor.suggest_meal(
                    user_message=input_data.user_message,
                )
                trace.append(TraceStep(
                    step="Life Skill",
                    detail=f"DietAdvisor: {life_advice.main_advice[:50]}",
                    data={"advice": life_advice.main_advice},
                ))
            
            elif intent.topic_area == "study":
                from .life_skills import StudyCoach
                coach = StudyCoach()
                
                # 判断是学习启动还是考前规划
                if any(kw in input_data.user_message for kw in ["学不进去", "不想学", "开始"]):
                    life_advice = await coach.help_start(input_data.user_message)
                elif any(kw in input_data.user_message for kw in ["ddl", "deadline", "作业"]):
                    life_advice = await coach.manage_deadline(input_data.user_message)
                else:
                    life_advice = await coach.plan_exam_prep(input_data.user_message)
                
                trace.append(TraceStep(
                    step="Life Skill",
                    detail=f"StudyCoach: {life_advice.main_advice[:50]}",
                    data={"advice": life_advice.main_advice},
                ))
            
            elif intent.topic_area == "social":
                from .life_skills import SocialAdvisor
                advisor = SocialAdvisor()
                
                if any(kw in input_data.user_message for kw in ["怎么回", "回消息", "回复"]):
                    life_advice = await advisor.suggest_reply(input_data.user_message)
                elif any(kw in input_data.user_message for kw in ["约", "表白", "约会"]):
                    life_advice = await advisor.date_advice(input_data.user_message)
                else:
                    life_advice = await advisor.boundary_advice(input_data.user_message)
                
                trace.append(TraceStep(
                    step="Life Skill",
                    detail=f"SocialAdvisor: {life_advice.main_advice[:50]}",
                    data={"advice": life_advice.main_advice},
                ))
        
        except Exception as e:
            trace.append(TraceStep(
                step="Life Skill",
                detail=f"Failed: {e}",
                data={"error": str(e)},
            ))
    
    # === Step 5: 技能选择（旧系统，用于 MCP 工具）===
    selected_skills = select_skills(signals, max_skills=2)
    
    # 根据新模式过滤技能
    if mode_decision.primary_mode == "chat":
        # Chat mode 只保留情绪陪伴类技能，过滤掉任务类
        selected_skills = [
            (s, m, sc) for s, m, sc in selected_skills
            if s.category in ("emotion", "easter_egg", "general")
        ]
    
    trace.append(TraceStep(
        step="Skill Selection",
        detail=f"Selected {len(selected_skills)} skills.",
        data=[{"id": s.id, "mode": m, "score": sc} for s, m, sc in selected_skills],
    ))
    
    # === Step 6: 构建上下文块 ===
    blocks: list[ContextBlock] = []
    
    # 核心块（新架构）
    core_blocks = _load_core_blocks_v2(
        input_data.character_id,
        input_data.character_prompt,
        mode_decision,
        intent,
    )
    blocks.extend(core_blocks)
    
    # 微胶囊（旧系统）
    state_tracker = get_state_tracker(input_data.user_id, input_data.conversation_id)
    capsules = build_capsules_from_signals(signals, state_tracker)
    for capsule in capsules:
        blocks.append(ContextBlock(
            id=f"capsule:{capsule.id}",
            type=capsule.type,  # type: ignore[arg-type]
            role="system",
            title=f"Capsule: {capsule.id}",
            content=capsule.content,
            priority=capsule.priority,
            tokens=estimate_tokens(capsule.content),
            source="signal_detector",
            reason=f"Signal confidence: {capsule.confidence:.2f}",
            position="before_history",
        ))
    
    # 生活能力建议（作为上下文注入）
    if life_advice:
        advice_content = f"""【生活建议参考】
{life_advice.main_advice}

具体选项：
"""
        for opt in life_advice.specific_options:
            advice_content += f"- {opt.get('name', '')}: {opt.get('action', '')}\n"
        
        if life_advice.context_note:
            advice_content += f"\n【回复提示】{life_advice.context_note}"
        
        blocks.append(ContextBlock(
            id=f"life_skill:{intent.topic_area}",
            type="skill",
            role="system",
            title=f"Life Skill: {intent.topic_area}",
            content=advice_content,
            priority=85,
            tokens=estimate_tokens(advice_content),
            source="life_skill",
            reason=f"Task mode life advice for {intent.topic_area}",
            position="before_history",
        ))
    
    # 技能 system prompt（旧系统）
    for skill, mode, score in selected_skills:
        if skill.system_prompt and mode in ("primary", "support"):
            # Chat mode 时简化技能 prompt
            if mode_decision.primary_mode == "chat":
                simplified = f"""用户可能需要：{skill.name}。
但当前是陪伴模式，不要切换成{skill.category}助手。
如果话题自然涉及，轻轻带过即可。"""
                blocks.append(ContextBlock(
                    id=f"skill:{skill.id}",
                    type="skill",
                    role="system",
                    title=f"Skill: {skill.name}",
                    content=simplified,
                    priority=82 if mode == "primary" else 78,
                    tokens=estimate_tokens(simplified),
                    source="skill_manifest",
                    reason=f"{mode} skill (chat mode simplified)",
                    position="before_history",
                ))
            else:
                blocks.append(ContextBlock(
                    id=f"skill:{skill.id}",
                    type="skill",
                    role="system",
                    title=f"Skill: {skill.name}",
                    content=skill.system_prompt,
                    priority=82 if mode == "primary" else 78,
                    tokens=estimate_tokens(skill.system_prompt),
                    source="skill_manifest",
                    reason=f"{mode} skill, score={score:.2f}",
                    position="before_history",
                ))
    
    # MCP 工具执行
    mcp_tool_results: list[dict[str, Any]] = []
    for skill, mode, score in selected_skills:
        if mode in ("primary", "support") and skill.id in ("radio_dj", "playlist_builder"):
            try:
                from prototype_demo.mcp_tools import execute_skill_mcp
                memory_context = {"home_city": "", "current_location": ""}
                result = execute_skill_mcp(skill.id, input_data.user_message, memory_context)
                if result and "formatted_context" in result:
                    mcp_tool_results.append({"skill": skill.id, "result": result})
                    blocks.append(ContextBlock(
                        id=f"mcp:{skill.id}",
                        type="skill",
                        role="system",
                        title=f"MCP Result: {skill.name}",
                        content=result["formatted_context"],
                        priority=80,
                        tokens=estimate_tokens(result["formatted_context"]),
                        source="mcp_tool",
                        reason=f"MCP tool for {skill.name}",
                        position="before_history",
                    ))
            except Exception as exc:
                trace.append(TraceStep(
                    step="MCP Tool",
                    detail=f"Failed: {exc}",
                    data={"error": str(exc)},
                ))
    
    # 作者注释 / 响应控制
    author_note = f"""【本轮响应要求】
- 模式：{mode_decision.primary_mode}（{mode_decision.user_intent}）
- 语调：{mode_decision.suggested_tone}
- 用户情绪：{intent.emotional_state}（强度{intent.emotional_intensity}）
- 关系时刻：{intent.relationship_moment}
- 用户期望：{intent.desired_action}

回复原则：
1. 先接话，不是先回答。接情绪/语气/潜台词。
2. Chat mode：短、自然、像日常对话。不要分析、不要总结。
3. Task mode：可以给建议，但要像朋友给建议，不是专家给方案。
4. 一轮最多一个问题。
5. 不要暴露系统、模式、检测器。
"""
    
    blocks.append(ContextBlock(
        id="author_note:current_turn",
        type="author_note",
        role="system",
        title="Response Control",
        content=author_note,
        priority=95,
        tokens=estimate_tokens(author_note),
        required=True,
        source="author_note",
        reason="Turn-level response control",
        position="after_history",
    ))
    
    # === Step 7: Token 预算 & 组装 ===
    max_input_tokens = 9000
    selected, removed, used_tokens = apply_token_budget(blocks, max_input_tokens)
    
    trace.append(TraceStep(
        step="Token Budget",
        detail=f"Selected {len(selected)} blocks, removed {len(removed)}.",
        data={"used_tokens": used_tokens},
    ))
    
    messages = compose_messages(
        selected,
        input_data.history[-8:],
        input_data.user_message,
    )
    
    # 路由结果
    route = RouteResult(
        intent=intent.topic_area if intent.topic_area != "others" else "casual_chat",  # type: ignore[arg-type]
        emotion=intent.emotional_state if intent.emotional_state in ["neutral", "happy", "anxious", "sad", "angry", "tired", "stressed"] else "neutral",  # type: ignore[arg-type]
        skills=[s[0].id for s in selected_skills],
        need_memory=False,
        need_lorebook=False,
        need_robot_context=False,
        response_style="short_warm" if mode_decision.primary_mode == "chat" else "structured",  # type: ignore[arg-type]
    )
    
    return ContextBuildResult(
        messages=messages,
        blocks=selected,
        route=route,
        token_summary=TokenSummary(
            max_input_tokens=max_input_tokens,
            used_tokens=used_tokens,
            removed_blocks=removed,
        ),
        trace=trace,
        mcp_tool_results=mcp_tool_results,
    )


# 兼容旧接口的 sync 版本（不推荐，但保留用于非 async 场景）
def build_context_v3_sync(input_data: ContextBuildInput) -> ContextBuildResult:
    """同步版本（降级用）"""
    try:
        return asyncio.run(build_context_v3(input_data))
    except Exception:
        # 如果 async 失败，回退到旧逻辑
        from .context_engine_v3_legacy import build_context_v3 as old_build
        return old_build(input_data)
