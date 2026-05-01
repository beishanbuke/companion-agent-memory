from __future__ import annotations

from .types import ContextBlock


def estimate_tokens(text: str) -> int:
    # Rough estimate: good enough for demo
    return max(1, len(text) // 2)


def apply_token_budget(
    blocks: list[ContextBlock],
    max_input_tokens: int,
) -> tuple[list[ContextBlock], list[ContextBlock], int]:
    required = [b for b in blocks if b.required]
    optional = sorted([b for b in blocks if not b.required], key=lambda b: b.priority, reverse=True)

    selected: list[ContextBlock] = []
    removed: list[ContextBlock] = []
    used_tokens = 0

    for b in required:
        selected.append(b)
        used_tokens += b.tokens

    for b in optional:
        if used_tokens + b.tokens <= max_input_tokens:
            selected.append(b)
            used_tokens += b.tokens
        else:
            removed.append(b)

    return selected, removed, used_tokens
