from __future__ import annotations

from .types import ChatMessage, ContextBlock


def compose_messages(
    blocks: list[ContextBlock],
    history: list[ChatMessage],
    current_user_message: str,
) -> list[dict[str, str]]:
    before_history = sorted(
        [b for b in blocks if b.position != "after_history"],
        key=lambda b: b.priority,
        reverse=True,
    )
    after_history = sorted(
        [b for b in blocks if b.position == "after_history"],
        key=lambda b: b.priority,
        reverse=True,
    )

    system_content = "\n\n".join(
        f"### {b.title}\n{b.content}" for b in before_history
    )

    post_history_content = "\n\n".join(
        f"### {b.title}\n{b.content}" for b in after_history
    )

    messages: list[dict[str, str]] = []

    if system_content.strip():
        messages.append({"role": "system", "content": system_content.strip()})

    for msg in history:
        messages.append(msg.to_dict())

    if post_history_content.strip():
        messages.append({"role": "system", "content": post_history_content.strip()})

    messages.append({"role": "user", "content": current_user_message})

    return messages
