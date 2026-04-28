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

from dataclasses import dataclass, field
from typing import Any

from .persona import SystemPersonaLayer, PersonaConfig
from .memory_adapter import MemoryLayerAdapter, TieredMemoryContext
from .memory_policy import MemoryUpdatePolicy, MemoryDecision
from .situation_router import SituationRouter, RoutingDecision
from .skill_registry import SkillRegistry
from .response_policy import ResponsePolicy, ResponseContext


@dataclass
class CompanionResult:
    """Result of processing a user message."""
    reply: str
    situation: str
    situation_confidence: float
    memory_decision: MemoryDecision
    memory_context: TieredMemoryContext
    skills_activated: list[str]
    memory_updated: bool
    safety_flag: bool
    system_prompt: str = ""
    debug_info: dict[str, Any] = field(default_factory=dict)


class CompanionAgentCore:
    """Main companion agent orchestrator."""

    def __init__(
        self,
        memory_engine: Any,
        persona_config: PersonaConfig | None = None,
        enable_llm_router: bool = True,
        enable_llm_memory_policy: bool = True,
    ):
        """Initialize the companion agent core.

        Args:
            memory_engine: Existing StructuredLongTermMemory instance
            persona_config: Optional custom persona configuration
            enable_llm_router: Whether to use LLM for situation classification
            enable_llm_memory_policy: Whether to use LLM for memory decisions
        """
        # Layers
        self.persona = SystemPersonaLayer(config=persona_config)
        self.memory = MemoryLayerAdapter(memory_engine)
        self.memory_policy = MemoryUpdatePolicy()
        self.router = SituationRouter()
        self.skills = SkillRegistry()
        self.response_policy = ResponsePolicy()

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

        # === Step 1: Situation Routing ===
        routing = await self.router.classify(user_message, history)

        # === Step 2: Memory Retrieval ===
        memory_context = TieredMemoryContext()
        if memory_enabled and routing.retrieve_memory:
            memory_context = await self.memory.retrieve_tiered(
                query=user_message,
                situation=routing.situation,
            )

        # === Step 3: Skill Resolution ===
        activated_skills = self.skills.resolve(routing.situation)
        skill_results = []
        for skill in activated_skills:
            result = await self.skills.execute(skill.name, {
                "user_message": user_message,
                "situation": routing.situation,
                "memory_context": memory_context,
            })
            skill_results.append(result)

        # === Step 4: Build System Prompt ===
        # Get memory profile hint
        profile = self.memory.get_profile_summary() if memory_enabled else {}

        system_prompt = self.persona.build_system_prompt(
            character_card_prompt=character_card_prompt,
            memory_profile=profile,
            situation=routing.situation,
        )

        # Add response policy suffix
        prompt_suffix = self.response_policy.build_prompt_suffix(routing, memory_context)
        if prompt_suffix:
            system_prompt = system_prompt + "\n\n" + prompt_suffix

        # === Step 5: Memory Update Policy ===
        memory_decision = MemoryDecision(
            action="ignore",
            reason="记忆已禁用或未触发",
            confidence=0.0,
            requires_confirmation=False,
            privacy_level="public",
            suggested_tags=[],
        )
        memory_updated = False

        if memory_enabled:
            snapshot = self._get_memory_snapshot()
            memory_decision = await self.memory_policy.evaluate(
                user_message=user_message,
                current_memory_snapshot=snapshot,
                situation=routing.situation,
            )

            if memory_decision.action in ("add", "update"):
                if not memory_decision.requires_confirmation:
                    await self.memory.store("user", user_message)
                    memory_updated = True
                # If requires_confirmation, we don't auto-store
                # The frontend should prompt the user

        # === Build Result ===
        return CompanionResult(
            reply="",  # To be filled by LLM caller
            situation=routing.situation,
            situation_confidence=routing.confidence,
            memory_decision=memory_decision,
            memory_context=memory_context,
            skills_activated=[s.name for s in activated_skills],
            memory_updated=memory_updated,
            safety_flag=routing.safety_flag,
            system_prompt=system_prompt,
            debug_info={
                "routing": {
                    "situation": routing.situation,
                    "confidence": routing.confidence,
                    "memory_tiers": routing.memory_tiers,
                    "call_tools": routing.call_tools,
                    "response_style": routing.response_style,
                },
                "memory": {
                    "action": memory_decision.action,
                    "reason": memory_decision.reason,
                    "confidence": memory_decision.confidence,
                    "requires_confirmation": memory_decision.requires_confirmation,
                },
                "skills": skill_results,
            },
        )

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
        if memory_section:
            messages.append({
                "role": "system",
                "content": f"以下是与用户相关的记忆信息，请自然地在回复中运用：\n\n{memory_section}",
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
        }
