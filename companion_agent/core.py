"""
Companion Agent Core

Main orchestrator that wires together all layers:
- SystemPersonaLayer
- MemoryLayerAdapter
- MemoryUpdatePolicy
- SituationRouter
- SkillRegistry
- ResponsePolicy

Usage:
    core = CompanionAgentCore(memory_engine)
    result = await core.process_message(
        user_message="我今天有点难过",
        conversation_history=[...],
    )
"""

from __future__ import annotations

import asyncio
import os
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .persona import SystemPersonaLayer, PersonaConfig
from .memory_adapter import MemoryLayerAdapter, TieredMemoryContext
from .memory_policy import MemoryUpdatePolicy, MemoryDecision
from .memory_router import MemoryRouter, MemoryRouteDecision
from .situation_router import SituationRouter, RoutingDecision
from .skill_registry import SkillRegistry
from .response_policy import ResponsePolicy, ResponseContext
from .emotion_detector import (
    CurrentEmotionDetector,
    EmotionDetection,
    EMOTION_NONE,
    LABEL_RESPONSE_GUIDANCE,
    NEGATIVE_LABELS,
)
from .emotion_memory import (
    EmotionBaseline,
    EmotionEventStore,
    build_followup_notes,
    detect_emotion_correction,
)

# Wave-1 LLM emotion-judge timeout: fast enough to keep reply latency
# intact; on timeout/slow network the detector falls back to the rule
# result and the slower background refine still upgrades the emotion board.
EMOTION_FAST_LLM_TIMEOUT = float(os.getenv("EMOTION_FAST_LLM_TIMEOUT", "1.2"))


# Single-worker executor serializing background memory stores across turns.
# stream_message drives asyncio via a per-request event loop (asyncio.run), so
# an asyncio.create_task store would be cancelled when that loop closes; a
# thread outlives it and overlaps with the main reply LLM. Cross-thread
# concurrent memory writes already exist (voice HTTPMemoryBackend), so the
# memory engine semantics stay unchanged.
_MEMORY_STORE_WORKER = ThreadPoolExecutor(
    max_workers=1, thread_name_prefix="companion-memory-store"
)


@dataclass
class CompanionResult:
    """Result of processing a user message."""
    reply: str
    situation: str
    situation_confidence: float
    memory_decision: MemoryDecision
    memory_context: TieredMemoryContext
    memory_route: MemoryRouteDecision
    emotion: EmotionDetection
    skills_activated: list[str]
    memory_updated: bool
    safety_flag: bool
    system_prompt: str = ""
    store_future: Any = field(default=None, repr=False)
    debug_info: dict[str, Any] = field(default_factory=dict)


class CompanionAgentCore:
    """Main companion agent orchestrator."""

    def __init__(
        self,
        memory_engine: Any,
        persona_config: PersonaConfig | None = None,
        enable_llm_router: bool = True,
        enable_llm_memory_policy: bool = True,
        emotion_state_dir: str | Path | None = None,
    ):
        """Initialize the companion agent core.

        Args:
            memory_engine: Existing StructuredLongTermMemory instance
            persona_config: Optional custom persona configuration
            enable_llm_router: Whether to use LLM for situation classification
            enable_llm_memory_policy: Whether to use LLM for memory decisions
            emotion_state_dir: Directory for emotion baseline/event stores
                (defaults to prototype_demo/.run via the emotion_memory module)
        """
        # Layers
        self.persona = SystemPersonaLayer(config=persona_config)
        self.memory = MemoryLayerAdapter(memory_engine)
        self.memory_policy = MemoryUpdatePolicy()
        self.router = SituationRouter()
        self.skills = SkillRegistry()
        self.response_policy = ResponsePolicy()
        self.memory_router = MemoryRouter()
        self.emotion_detector = CurrentEmotionDetector()
        state_dir = Path(emotion_state_dir) if emotion_state_dir else None
        self.emotion_baseline = (
            EmotionBaseline(state_dir / "emotion_baseline.json") if state_dir else EmotionBaseline()
        )
        self.emotion_events = (
            EmotionEventStore(state_dir / "emotion_events.json") if state_dir else EmotionEventStore()
        )

        # Config
        self._enable_llm_router = enable_llm_router
        self._enable_llm_memory_policy = enable_llm_memory_policy

    async def process_message(
        self,
        user_message: str,
        conversation_history: list[dict[str, str]] | None = None,
        character_card_prompt: str = "",
        memory_enabled: bool = True,
    ) -> CompanionResult:
        """Process a user message through all layers.

        This is the main entry point for the companion agent.
        """
        history = conversation_history or []
        t_start = time.perf_counter()
        snapshot = self._get_memory_snapshot() if memory_enabled else {}
        profile = self.memory.get_profile_summary() if memory_enabled else {}
        t_snapshot = time.perf_counter()

        # Keyword pre-classification gives the memory policy a situation hint
        # so it can run in parallel with the (possibly LLM-backed) router.
        # The final routing decision still comes from router.classify().
        policy_situation, _ = self.router.keyword_classify(user_message)

        stage_ms: dict[str, float] = {}

        async def _timed(name: str, coro: Any) -> Any:
            t0 = time.perf_counter()
            try:
                return await coro
            finally:
                stage_ms[name] = round((time.perf_counter() - t0) * 1000, 1)

        # === Wave 1 (parallel): emotion detect. A fast LLM judge attempt
        # (~1.2s) runs in a worker thread alongside routing/policy; on
        # timeout or failure the detector falls back to the rule result.
        # The slower background refine only launches when the fast pass
        # did not reach the LLM (see emotion_refine_future below).
        recent_emotional_state = str(profile.get("emotional_state") or "")
        behavioral = self.emotion_baseline.features(user_message, history)
        correction = detect_emotion_correction(user_message)

        async def _fast_emotion() -> EmotionDetection:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(
                None,
                lambda: self.emotion_detector.detect(
                    user_message,
                    history,
                    recent_emotional_state,
                    llm_timeout=EMOTION_FAST_LLM_TIMEOUT,
                    behavioral_signals=behavioral,
                ),
            )

        emotion_coro = _timed("emotion", _fast_emotion())
        routing_coro = _timed(
            "routing",
            self.router.classify(user_message, history, use_llm=self._enable_llm_router),
        )
        if memory_enabled:
            policy_coro = _timed(
                "policy",
                self.memory_policy.evaluate(
                    user_message=user_message,
                    current_memory_snapshot=snapshot,
                    situation=policy_situation,
                    use_llm=self._enable_llm_memory_policy,
                ),
            )
            emotion, routing, memory_decision = await asyncio.gather(
                emotion_coro, routing_coro, policy_coro
            )
        else:
            emotion, routing = await asyncio.gather(emotion_coro, routing_coro)
            memory_decision = MemoryDecision(
                action="ignore",
                reason="记忆已禁用或未触发",
                confidence=0.0,
                requires_confirmation=False,
                privacy_level="public",
                suggested_tags=[],
            )
        t_wave1 = time.perf_counter()

        # 用户纠错优先：显式的"我不是X，是Y"覆盖任何推断结果
        if correction is not None:
            emotion = EmotionDetection(
                label=correction.correct_label,
                intensity=max(emotion.intensity, 0.6),
                confidence=max(emotion.confidence, 0.8),
                reason=(
                    f"{emotion.reason};user_correction:"
                    f"{correction.wrong_label}->{correction.correct_label}"
                ),
                signals=[*emotion.signals, "user_correction"],
                trend=emotion.trend,
                context_turns=emotion.context_turns,
                secondary_label=emotion.secondary_label,
                secondary_intensity=emotion.secondary_intensity,
            )

        # 情绪事件沉淀 + 用户基线更新（纵向理解的原料；JSON 写入是毫秒级）
        if emotion.label != EMOTION_NONE and (
            emotion.label in NEGATIVE_LABELS or emotion.intensity >= 0.6
        ):
            self.emotion_events.record(
                emotion.label,
                emotion.intensity,
                user_message,
                trend=emotion.trend,
                corrected=correction is not None,
            )
        self.emotion_baseline.update(user_message)

        # 后台 LLM 情绪精修：仅当 Wave-1 快检没拿到有效 LLM 结果时启动
        # （默认更长超时），完成后经 done callback 回写 debug_info["emotion"]，
        # 由 server 在 final 后持久化到情绪看板。
        got_llm_judge = (
            "llm_judge" in emotion.signals
            and "llm_judge_failed" not in emotion.signals
            and "invalid_llm_label" not in emotion.signals
        )
        emotion_refine_future = None
        if not got_llm_judge:
            emotion_refine_future = asyncio.get_running_loop().run_in_executor(
                None,
                lambda: self.emotion_detector.detect(
                    user_message,
                    history,
                    recent_emotional_state,
                    behavioral_signals=behavioral,
                ),
            )

        memory_route = self.memory_router.route(
            user_message=user_message,
            conversation_history=history,
            situation=routing.situation,
            situation_confidence=routing.confidence,
            current_memory_snapshot=snapshot,
        )

        # === Step 2: Memory Retrieval ===
        t_retrieve0 = time.perf_counter()
        memory_context = TieredMemoryContext()
        if memory_enabled and memory_route.need_memory:
            memory_context = await self.memory.retrieve_tiered(
                query=user_message,
                situation=routing.situation,
                tiers=memory_route.tiers,
                max_per_tier=memory_route.max_per_tier,
                limit=memory_route.max_items,
            )
        stage_ms["retrieve"] = round((time.perf_counter() - t_retrieve0) * 1000, 1)

        # === Step 3: Skill Resolution ===
        t_skills0 = time.perf_counter()
        activated_skills = self.skills.resolve(routing.situation)
        skill_results = []
        for skill in activated_skills:
            result = await self.skills.execute(skill.name, {
                "user_message": user_message,
                "situation": routing.situation,
                "memory_context": memory_context,
            })
            skill_results.append(result)
        stage_ms["skills"] = round((time.perf_counter() - t_skills0) * 1000, 1)

        # === Step 4: Build System Prompt ===
        # Get memory profile hint
        system_prompt = self.persona.build_system_prompt(
            character_card_prompt=character_card_prompt,
            memory_profile=profile if memory_route.need_memory else {},
            situation=routing.situation,
        )
        emotion_lines = [
            "",
            "【本轮情绪线索】",
            (
                f"当前推断：{emotion.label}（强度 {emotion.intensity:.2f}，"
                f"置信度 {emotion.confidence:.2f}，趋势 {emotion.trend}）。"
            ),
        ]
        if emotion.secondary_label != EMOTION_NONE and emotion.secondary_intensity > 0:
            emotion_lines.append(
                f"伴随情绪：{emotion.secondary_label}"
                f"（强度 {emotion.secondary_intensity:.2f}），回应时两者都要照顾到。"
            )
        guidance = LABEL_RESPONSE_GUIDANCE.get(emotion.label)
        if emotion.label != EMOTION_NONE and emotion.confidence >= 0.55 and guidance:
            emotion_lines.append(f"回应倾向：{guidance}")
        elif emotion.label != EMOTION_NONE and emotion.confidence < 0.55:
            emotion_lines.append(
                "置信度偏低：用温和中性的语气回应，不做强烈的情绪定性。"
            )
        if correction is not None:
            emotion_lines.append(
                f"用户刚纠正过情绪判断（不是{correction.wrong_label}，"
                f"而是{correction.correct_label}）：以纠正后的为准，"
                "可以自然地接住这个纠正。"
            )
        followups = build_followup_notes(self.emotion_events, current_trigger=user_message)
        if followups:
            emotion_lines.append("【情绪跟进】")
            emotion_lines.extend(followups)
        emotion_lines.append(
            "以上仅是回应语气的参考，不要把它当作事实向用户断言；"
            "以用户当前表达为准，避免被早先情绪绑住。"
        )
        system_prompt += "\n\n" + "\n".join(emotion_lines)

        # Add response policy suffix
        prompt_suffix = self.response_policy.build_prompt_suffix(routing, memory_context, memory_route)
        if prompt_suffix:
            system_prompt = system_prompt + "\n\n" + prompt_suffix

        # === Step 5: Memory Update Policy ===
        store_future = None
        memory_updated = False

        if (
            memory_enabled
            and memory_decision.action in ("add", "update")
            and not memory_decision.requires_confirmation
        ):
            # Background store: overlaps with the main reply LLM instead of
            # blocking response generation. Failures are logged, never raised.
            t_store0 = time.perf_counter()
            store_future = self._schedule_background_store(user_message)
            memory_updated = True
            stage_ms["store_schedule"] = round((time.perf_counter() - t_store0) * 1000, 1)
        # If requires_confirmation, we don't auto-store
        # The frontend should prompt the user

        core_timings = {
            "snapshot_ms": round((t_snapshot - t_start) * 1000, 1),
            "wave1_ms": round((t_wave1 - t_snapshot) * 1000, 1),
            "emotion_ms": stage_ms.get("emotion", 0.0),
            "routing_ms": stage_ms.get("routing", 0.0),
            "policy_ms": stage_ms.get("policy", 0.0),
            "retrieve_ms": stage_ms.get("retrieve", 0.0),
            "skills_ms": stage_ms.get("skills", 0.0),
            "store_schedule_ms": stage_ms.get("store_schedule", 0.0),
            "total_ms": round((time.perf_counter() - t_start) * 1000, 1),
        }

        # === Build Result ===
        result = CompanionResult(
            reply="",  # To be filled by LLM caller
            situation=routing.situation,
            situation_confidence=routing.confidence,
            memory_decision=memory_decision,
            memory_context=memory_context,
            memory_route=memory_route,
            emotion=emotion,
            skills_activated=[s.name for s in activated_skills],
            memory_updated=memory_updated,
            safety_flag=routing.safety_flag,
            system_prompt=system_prompt,
            store_future=store_future,
            debug_info={
                "core_timings": core_timings,
                "routing": {
                    "situation": routing.situation,
                    "confidence": routing.confidence,
                    "memory_tiers": routing.memory_tiers,
                    "call_tools": routing.call_tools,
                    "response_style": routing.response_style,
                },
                "memory_route": {
                    "need_memory": memory_route.need_memory,
                    "retrieval_mode": memory_route.retrieval_mode,
                    "tiers": memory_route.tiers,
                    "mention_policy": memory_route.mention_policy,
                    "reason": memory_route.reason,
                    "strategy_version": memory_route.strategy_version,
                    "confidence": memory_route.confidence,
                    "signals": memory_route.signals,
                    "tier_scores": memory_route.tier_scores,
                },
                "memory": {
                    "action": memory_decision.action,
                    "reason": memory_decision.reason,
                    "confidence": memory_decision.confidence,
                    "requires_confirmation": memory_decision.requires_confirmation,
                    "lifecycle_trace": memory_context.lifecycle_trace,
                },
                "emotion": {
                    "label": emotion.label,
                    "intensity": emotion.intensity,
                    "confidence": emotion.confidence,
                    "reason": emotion.reason,
                    "signals": emotion.signals,
                    "trend": emotion.trend,
                    "context_turns": emotion.context_turns,
                    "secondary_label": emotion.secondary_label,
                    "secondary_intensity": emotion.secondary_intensity,
                },
                "skills": skill_results,
            },
        )
        result.emotion_refine_future = emotion_refine_future

        def _write_refined_emotion(fut) -> None:
            try:
                refined = fut.result()
            except Exception:
                return
            try:
                result.debug_info["emotion"] = {
                    "label": refined.label,
                    "intensity": refined.intensity,
                    "confidence": refined.confidence,
                    "reason": refined.reason,
                    "signals": refined.signals,
                    "trend": refined.trend,
                    "context_turns": refined.context_turns,
                    "secondary_label": refined.secondary_label,
                    "secondary_intensity": refined.secondary_intensity,
                }
            except Exception:
                pass

        if emotion_refine_future is not None:
            emotion_refine_future.add_done_callback(_write_refined_emotion)
        return result

    def build_messages_for_llm(
        self,
        result: CompanionResult,
        user_message: str,
        history: list[dict[str, str]],
    ) -> list[dict[str, str]]:
        """Build the message list for LLM completion.

        This should be called after process_message() to get the system prompt.
        """
        messages = []

        # System prompt
        messages.append({
            "role": "system",
            "content": result.system_prompt,
        })

        # Add memory context as a system message (if available)
        memory_section = result.memory_context.to_prompt_section()
        if memory_section and result.memory_route.need_memory:
            if result.memory_route.mention_policy == "explicit_ok":
                memory_prefix = "以下是与用户相关的记忆信息，可直接用来回答用户的记忆相关问题：\n\n"
            else:
                memory_prefix = (
                    "以下是与用户相关的背景信息。若这些信息与当前问题相关，"
                    "必须据此给出个性化回答；不要主动提及“你之前说过”或“我记得”：\n\n"
                )
            messages.append({
                "role": "system",
                "content": f"{memory_prefix}{memory_section}",
            })

        # Conversation history
        for msg in history[-10:]:  # Last 10 messages
            messages.append(msg)

        # Current user message
        messages.append({
            "role": "user",
            "content": user_message,
        })

        return messages

    def format_response(
        self,
        raw_response: str,
        result: CompanionResult,
        user_message: str,
        history: list[dict[str, str]],
    ) -> str:
        """Format the LLM response."""
        response_ctx = ResponseContext(
            user_message=user_message,
            situation=result.situation,
            memory_context=result.memory_context,
            skill_results=[],
            conversation_history=history,
            safety_flag=result.safety_flag,
        )
        return self.response_policy.format_response(raw_response, response_ctx)

    def _schedule_background_store(self, content: str):
        """Queue a user-turn memory store on the shared single-worker executor.

        Returns a concurrent.futures.Future the caller may wait on before
        diffing memory snapshots. Exceptions inside the store are caught and
        logged so a failed write never breaks the conversation.
        """
        def _run() -> None:
            try:
                asyncio.run(self.memory.store("user", content))
            except Exception as exc:  # noqa: BLE001
                print(f"[companion-core] background memory store failed: {exc}", flush=True)

        return _MEMORY_STORE_WORKER.submit(_run)

    def _get_memory_snapshot(self) -> dict[str, Any]:
        """Get memory snapshot for policy evaluation."""
        return self.memory._engine.snapshot()

    def get_status(self) -> dict[str, Any]:
        """Get current agent status for frontend display."""
        return {
            "persona_name": self.persona.config.name,
            "persona_identity": self.persona.config.identity,
            "available_skills": self.skills.get_skill_descriptions(),
            "situations": self.router.get_all_situations(),
            "proactive_enabled": self.response_policy.proactive_enabled,
            "memory_router_version": self.memory_router.version,
            "memory_lifecycle_enabled": True,
        }
