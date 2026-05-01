from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .types import ContextBlock
from .token_budget import estimate_tokens


@dataclass
class UserMemory:
    id: str
    user_id: str
    type: str  # profile | preference | event | emotion_pattern
    text: str
    tags: list[str]
    importance: float
    updated_at: str


MOCK_MEMORIES: list[UserMemory] = [
    UserMemory(
        id="m1",
        user_id="demo-user",
        type="preference",
        text="用户喜欢回复先给结论，再给清晰分点，不喜欢空泛鼓励。",
        tags=["style", "preference"],
        importance=0.9,
        updated_at="2026-04-20",
    ),
    UserMemory(
        id="m2",
        user_id="demo-user",
        type="event",
        text="用户最近在做 AI companion / agent-robot personalized education 项目，需要准备展示和技术方案。",
        tags=["project", "presentation", "agent"],
        importance=0.95,
        updated_at="2026-04-29",
    ),
    UserMemory(
        id="m3",
        user_id="demo-user",
        type="emotion_pattern",
        text="用户在考试、DDL、presentation 前容易焦虑，但更适合短计划和明确下一步，而不是长篇安慰。",
        tags=["exam", "stress", "planning"],
        importance=0.85,
        updated_at="2026-04-18",
    ),
]


def _keyword_score(memory: UserMemory, text: str) -> float:
    lower = text.lower()
    score = 0.0

    for tag in memory.tags:
        if tag.lower() in lower:
            score += 0.25

    for word in re.split(r"[，。,. /]", memory.text):
        if len(word) >= 2 and word.lower() in lower:
            score += 0.05

    return min(1.0, score + memory.importance * 0.3)


def retrieve_memory_blocks(
    user_id: str,
    user_message: str,
    top_k: int = 3,
) -> list[ContextBlock]:
    import re

    scored = []
    for m in MOCK_MEMORIES:
        if m.user_id == user_id:
            score = _keyword_score(m, user_message)
            if score > 0.25:
                scored.append((m, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    selected = scored[:top_k]

    blocks: list[ContextBlock] = []
    for memory, score in selected:
        content = f"[Memory: {memory.type}]\n{memory.text}"
        blocks.append(
            ContextBlock(
                id=f"memory:{memory.id}",
                type="memory",
                role="system",
                title=f"Memory: {memory.type}",
                content=content,
                priority=round(70 + score * 15),
                tokens=estimate_tokens(content),
                source="memory_store",
                reason=f"Relevant memory, score={score:.2f}, tags={', '.join(memory.tags)}",
                position="before_history",
            )
        )
    return blocks
