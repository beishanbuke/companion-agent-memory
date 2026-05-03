"""Companion Agent v2 - 本科生陪伴 Agent 升级架构"""

from .core_v2 import CompanionAgentCoreV2, CompanionResultV2
from .intent_engine import IntentEngine, IntentAnalysis
from .state_tracker import StateTracker, ConversationState
from .thread_manager import ThreadManager, Thread
from .policy_planner import PolicyPlanner, TurnPolicy
from .context_assembler import ContextAssembler, ContextBlock
from .tool_contract import ToolRegistry, ToolResult, ToolContract, get_tool_registry
from .dual_brain import DualBrainRouter, BrainMode
from .persona_v2 import PersonaV2, CharacterStyle, EXAMPLE_DIALOGUES
from .life_skills import LifeSkillsEngine, LifeAdvice
from .response_judge import ResponseJudge, JudgeResult

__all__ = [
    "CompanionAgentCoreV2",
    "CompanionResultV2",
    "IntentEngine",
    "IntentAnalysis",
    "StateTracker",
    "ConversationState",
    "ThreadManager",
    "Thread",
    "PolicyPlanner",
    "TurnPolicy",
    "ContextAssembler",
    "ContextBlock",
    "ToolRegistry",
    "ToolResult",
    "ToolContract",
    "get_tool_registry",
    "DualBrainRouter",
    "BrainMode",
    "PersonaV2",
    "CharacterStyle",
    "EXAMPLE_DIALOGUES",
    "LifeSkillsEngine",
    "LifeAdvice",
    "ResponseJudge",
    "JudgeResult",
]