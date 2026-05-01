from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .types import ContextBlock
from .token_budget import estimate_tokens


@dataclass
class LorebookEntry:
    id: str
    title: str
    keys: list[str]
    secondary_keys: list[str] | None = None
    content: str = ""
    priority: int = 80
    position: str = "before_history"
    enabled: bool = True
    recursive: bool = False


LOREBOOK: list[LorebookEntry] = [
    LorebookEntry(
        id="exam_stress",
        title="考试压力场景",
        keys=["考试", "复习", "quiz", "midterm", "final", "学不进去"],
        content=(
            "当前场景：用户处于考试或复习压力中。"
            "回复应先降低心理负担，再给出非常小的下一步行动。"
            "避免长篇鸡汤，优先给 15-25 分钟可执行计划。"
        ),
        priority=82,
        position="before_history",
        enabled=True,
        recursive=True,
    ),
    LorebookEntry(
        id="late_night_dorm",
        title="深夜宿舍场景",
        keys=["宿舍", "深夜", "睡不着", "两点", "熬夜"],
        content=(
            "当前场景：用户可能在深夜宿舍中聊天。"
            "回复应更轻、更短、更像陪伴，不要安排过重任务。"
            "可以建议低负担收尾动作。"
        ),
        priority=78,
        position="before_history",
        enabled=True,
        recursive=True,
    ),
    LorebookEntry(
        id="presentation_help",
        title="展示/汇报准备场景",
        keys=["presentation", "展示", "答辩", "汇报", "演讲"],
        content=(
            "当前任务：用户需要准备展示。"
            "回复应优先给结构、讲稿逻辑、过渡句和可展示亮点，"
            "而不是泛泛建议。"
        ),
        priority=80,
        position="before_history",
        enabled=True,
    ),
    LorebookEntry(
        id="robot_comfort_action",
        title="机器人安慰动作",
        keys=["机器人", "动作", "抱抱", "点头", "表情", "安慰"],
        content=(
            "机器人能力上下文：机器人可以执行轻微点头、屏幕表情变化、"
            "语音回复、呼吸灯渐变、简单手势。"
            "不要承诺无法执行的复杂物理动作。"
        ),
        priority=86,
        position="before_history",
        enabled=True,
    ),
]


def _match_entry(entry: LorebookEntry, scan_text: str) -> bool:
    scan_lower = scan_text.lower()
    primary_hit = any(k.lower() in scan_lower for k in entry.keys)
    if not primary_hit:
        return False
    if not entry.secondary_keys:
        return True
    return any(k.lower() in scan_lower for k in entry.secondary_keys)


def retrieve_lorebook_blocks(
    current_user_message: str,
    recent_history_text: str,
    max_recursive_depth: int = 1,
) -> list[ContextBlock]:
    scan_text = f"{recent_history_text}\n{current_user_message}"
    selected: list[LorebookEntry] = []
    selected_ids: set[str] = set()

    for depth in range(max_recursive_depth + 1):
        newly_matched = [
            entry
            for entry in LOREBOOK
            if entry.enabled and entry.id not in selected_ids and _match_entry(entry, scan_text)
        ]
        if not newly_matched:
            break
        for entry in newly_matched:
            selected.append(entry)
            selected_ids.add(entry.id)
            if entry.recursive:
                scan_text += f"\n{entry.content}"

    selected.sort(key=lambda e: e.priority, reverse=True)

    blocks: list[ContextBlock] = []
    for entry in selected:
        content = f"[Context: {entry.title}]\n{entry.content}"
        blocks.append(
            ContextBlock(
                id=f"lorebook:{entry.id}",
                type="lorebook",
                role="system",
                title=entry.title,
                content=content,
                priority=entry.priority,
                tokens=estimate_tokens(content),
                source="lorebook",
                reason=f"Triggered by keywords: {', '.join(entry.keys)}",
                position=entry.position,  # type: ignore[arg-type]
            )
        )
    return blocks
