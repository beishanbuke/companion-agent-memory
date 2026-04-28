"""
Companion Agent Core - Architecture Document

This module provides a layered architecture for a companion-style AI agent
without modifying the existing memory module.

## Architecture

CompanionAgentCore
├── SystemPersonaLayer          # Fixed personality, tone, safety rules
├── MemoryLayerAdapter          # 5-tier memory read interface (adapter pattern)
├── MemoryUpdatePolicy          # Per-turn memory update decisions
├── SituationRouter             # Intent classification & routing
├── SkillRegistry               # Skill loading and execution
└── ResponsePolicy              # Response orchestration

## Design Principles

1. **Memory Module Immutable**: All memory operations go through adapter,
   never modify memory/ directory.
2. **Layered Abstraction**: Each layer is independently testable.
3. **Minimal MVP**: First implement 4 core modules, then extend.
4. **Explicit over Implicit**: All decisions (memory, routing, skills) are
   observable and logged.

## Memory 5-Tier Model

The adapter maps StructuredLongTermMemory into 5 conceptual tiers:
- profile: persona_slots (stable user facts)
- preferences: preference_slots + preference_profiles
- long_term_goals: derived from events + explicit goals
- episodic_events: event-type memories
- safety_notes: tagged sensitive/important memories

## Situation Categories

- casual_chat: General conversation
- emotional_support: Emotional companionship
- planning: Task/schedule planning
- music_companion: Music-related
- learning_coach: Learning/study help
- coding_helper: Code assistance
- memory_query: "Do you remember..."
- tool_task: Needs MCP/tool call
- safety_sensitive: Risky content
- personal_routine: Daily life habits

## Skill Tiers

- Tier 1 (Built-in): emotional-companion, memory-manager
- Tier 2 (Domain): music-dj, study-coach, daily-review
- Tier 3 (External): frontend-refactor, github-helper, etc.

## Integration Flow

1. User sends message
2. SituationRouter.classify() -> situation
3. MemoryLayerAdapter.retrieve_tiered() -> memory_context
4. SkillRegistry.resolve_skills(situation) -> skills
5. SystemPersonaLayer.build_prompt() -> system_prompt
6. LLM generates response
7. MemoryUpdatePolicy.evaluate() -> update decision
8. If update: MemoryLayerAdapter.store()
9. ResponsePolicy.format() -> final response
"""

from .core import CompanionAgentCore
from .persona import SystemPersonaLayer
from .memory_adapter import MemoryLayerAdapter
from .memory_policy import MemoryUpdatePolicy
from .situation_router import SituationRouter
from .skill_registry import SkillRegistry
from .response_policy import ResponsePolicy

__all__ = [
    "CompanionAgentCore",
    "SystemPersonaLayer",
    "MemoryLayerAdapter",
    "MemoryUpdatePolicy",
    "SituationRouter",
    "SkillRegistry",
    "ResponsePolicy",
]
