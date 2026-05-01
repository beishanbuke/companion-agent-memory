from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

ContextBlockType = Literal[
    "system", "persona", "user_profile", "memory", "lorebook",
    "skill", "history", "author_note", "safety", "debug"
]

ContextRole = Literal["system", "user", "assistant"]


@dataclass
class ContextBlock:
    id: str
    type: ContextBlockType
    role: ContextRole
    title: str
    content: str
    priority: int
    tokens: int
    required: bool = False
    source: str = ""
    reason: str = ""
    position: Literal["before_history", "in_history", "after_history"] = "before_history"


@dataclass
class RouteResult:
    intent: Literal[
        "casual_chat", "academic_help", "emotional_support",
        "planning", "memory_recall", "robot_action", "crisis", "unknown"
    ] = "casual_chat"
    emotion: Literal[
        "neutral", "happy", "anxious", "sad", "angry", "tired", "stressed"
    ] = "neutral"
    skills: list[str] = field(default_factory=list)
    need_memory: bool = False
    need_lorebook: bool = True
    need_robot_context: bool = False
    response_style: Literal[
        "short_warm", "structured", "comforting", "playful", "technical"
    ] = "short_warm"


@dataclass
class ChatMessage:
    role: Literal["user", "assistant", "system"]
    content: str

    def to_dict(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}


@dataclass
class ContextBuildInput:
    user_id: str
    character_id: str
    conversation_id: str
    user_message: str
    history: list[ChatMessage] = field(default_factory=list)
    debug: bool = False
    demo_id: str = ""
    character_prompt: str = ""


@dataclass
class TokenSummary:
    max_input_tokens: int = 9000
    used_tokens: int = 0
    removed_blocks: list[ContextBlock] = field(default_factory=list)


@dataclass
class TraceStep:
    step: str
    detail: str
    data: Any = None


@dataclass
class ContextBuildResult:
    messages: list[dict[str, str]] = field(default_factory=list)
    blocks: list[ContextBlock] = field(default_factory=list)
    route: RouteResult = field(default_factory=RouteResult)
    token_summary: TokenSummary = field(default_factory=TokenSummary)
    trace: list[TraceStep] = field(default_factory=list)
    mcp_tool_results: list[dict[str, Any]] = field(default_factory=list)
