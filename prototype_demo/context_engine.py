from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent
STRATEGY_FILE = BASE_DIR / "scene_strategies.json"

MEMORY_PROBE_PATTERNS = (
    r"^你还记得",
    r"^你记得",
    r"^还记得我",
    r"^我叫什么",
    r"^我住哪",
    r"^我住哪里",
    r"^我喜欢什么",
    r"^do you remember",
    r"^what do you remember",
    r"^can you remember",
    r"^what is my name",
    r"^where do i live",
)

EMOTIONAL_CUES = (
    "难过",
    "焦虑",
    "压力",
    "崩溃",
    "委屈",
    "烦",
    "痛苦",
    "孤独",
    "伤心",
    "抑郁",
    "upset",
    "anxious",
    "stressed",
    "sad",
    "lonely",
)

TASK_CUES = (
    "帮我",
    "请你",
    "给我",
    "总结",
    "改写",
    "润色",
    "翻译",
    "列",
    "计划",
    "步骤",
    "to-do",
    "todo",
    "rewrite",
    "summarize",
    "plan",
)

KNOWLEDGE_CUES = (
    "是什么",
    "为什么",
    "怎么",
    "区别",
    "原理",
    "解释",
    "what is",
    "why",
    "how",
    "difference",
    "explain",
)

SCENE_MEMORY_CONFIG: dict[str, dict[str, Any]] = {
    "default": {"limit": 5, "filters": {"active_only": True, "scene": "default"}},
    "smalltalk": {
        "limit": 5,
        "filters": {"memory_types": ["persona", "preference", "event"], "active_only": True, "scene": "smalltalk"},
    },
    "emotional_support": {
        "limit": 6,
        "filters": {
            "memory_types": ["event", "preference", "persona"],
            "slot_keys": ["relationship_status", "work_context", "social_style", "activity_style"],
            "active_only": True,
            "scene": "emotional_support",
        },
    },
    "knowledge_qa": {
        "limit": 4,
        "filters": {"memory_types": ["persona", "event"], "active_only": True, "scene": "knowledge_qa"},
    },
    "task_execution": {
        "limit": 5,
        "filters": {
            "memory_types": ["preference", "persona", "event"],
            "active_only": True,
            "scene": "task_execution",
        },
    },
    "memory_probe": {
        "limit": 7,
        "filters": {
            "memory_types": ["persona", "preference", "event"],
            "active_only": True,
            "scene": "memory_probe",
        },
    },
}


@dataclass
class ContextPackResult:
    scene: str
    messages: list[dict[str, str]]
    memory_filters: dict[str, Any]
    memory_limit: int
    history_window: int


def load_scene_strategies(path: Path = STRATEGY_FILE) -> dict[str, dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    if "default" not in payload:
        payload["default"] = {
            "tone": "自然、口语、真诚，不背诵",
            "response_rules": ["优先回应用户当前意图。"],
            "memory_focus": "仅使用明显相关的长期记忆。",
        }
    return payload


def detect_scene(user_message: str) -> str:
    text = (user_message or "").strip()
    lowered = text.lower()

    if any(re.search(pattern, lowered) for pattern in MEMORY_PROBE_PATTERNS):
        return "memory_probe"
    if any(cue in text or cue in lowered for cue in EMOTIONAL_CUES):
        return "emotional_support"
    if any(cue in text or cue in lowered for cue in TASK_CUES):
        return "task_execution"
    if any(cue in text or cue in lowered for cue in KNOWLEDGE_CUES) or text.endswith("?") or text.endswith("？"):
        return "knowledge_qa"
    return "smalltalk"


def memory_query_options(scene: str, rerank_enabled: bool) -> tuple[dict[str, Any], int]:
    config = SCENE_MEMORY_CONFIG.get(scene) or SCENE_MEMORY_CONFIG["default"]
    filters = dict(config.get("filters") or {})
    limit = int(config.get("limit") or SCENE_MEMORY_CONFIG["default"]["limit"])
    if not rerank_enabled:
        filters.pop("scene", None)
    return filters, limit


def _history_window_for_scene(scene: str) -> int:
    return {
        "smalltalk": 8,
        "emotional_support": 10,
        "task_execution": 8,
        "knowledge_qa": 8,
        "memory_probe": 6,
    }.get(scene, 8)


def _summarize_ncp_results(ncp_payload: dict[str, Any]) -> str:
    results = ncp_payload.get("results") or []
    if not isinstance(results, list) or not results:
        return ""

    summary_lines = []
    for item in results[:4]:
        if not isinstance(item, dict):
            continue
        tool = str(item.get("tool") or "tool")
        requirement = str(item.get("requirement") or "")
        data = item.get("data")
        if isinstance(data, list):
            detail = f"命中 {len(data)} 条"
        elif isinstance(data, dict):
            detail = f"返回 {len(data)} 个字段"
        else:
            detail = "返回结果可用"
        summary_lines.append(f"- {tool}: {requirement or '已执行'} ({detail})")

    if not summary_lines:
        return ""
    return "NCP 工具结果摘要:\n" + "\n".join(summary_lines)


def _scene_instruction(scene: str, strategies: dict[str, dict[str, Any]]) -> str:
    strategy = strategies.get(scene) or strategies.get("default") or {}
    tone = str(strategy.get("tone") or "自然、口语、真诚")
    memory_focus = str(strategy.get("memory_focus") or "仅使用明显相关的长期记忆")
    rules = strategy.get("response_rules") or []
    if not isinstance(rules, list):
        rules = []
    rendered_rules = "\n".join(f"- {str(rule)}" for rule in rules[:5])

    return (
        "[场景策略]\n"
        f"当前场景: {scene}\n"
        f"语气要求: {tone}\n"
        "执行规则:\n"
        f"{rendered_rules or '- 优先回应用户当前意图。'}\n"
        f"记忆使用: {memory_focus}"
    )


def pack_context_messages(
    *,
    base_system_prompt: str,
    user_message: str,
    short_history: list[dict[str, str]],
    memory_text: str,
    ncp_payload: dict[str, Any],
    strategies: dict[str, dict[str, Any]],
    scene_router_enabled: bool,
    context_packer_enabled: bool,
    rerank_enabled: bool,
) -> ContextPackResult:
    scene = detect_scene(user_message) if scene_router_enabled else "default"
    memory_filters, memory_limit = memory_query_options(scene, rerank_enabled)
    history_window = _history_window_for_scene(scene) if context_packer_enabled else 12

    messages: list[dict[str, str]] = [
        {"role": "system", "content": base_system_prompt.strip()}
    ]

    if context_packer_enabled:
        messages.append({"role": "system", "content": _scene_instruction(scene, strategies)})

    if memory_text:
        messages.append(
            {
                "role": "system",
                "content": "以下是与当前用户相关的长期记忆，请仅引用与当前问题强相关的信息:\n" + memory_text,
            }
        )

    if ncp_payload.get("invoked") and ncp_payload.get("context_text"):
        if context_packer_enabled:
            summary = _summarize_ncp_results(ncp_payload)
            if summary:
                messages.append({"role": "system", "content": summary})
        messages.append(
            {
                "role": "system",
                "content": "以下是工具通道返回的事实数据。请把它当作外部事实来源，转写为自然口语回答。",
            }
        )
        messages.append({"role": "system", "content": str(ncp_payload["context_text"])})

    messages.extend(short_history[-history_window:])
    messages.append({"role": "user", "content": user_message})

    return ContextPackResult(
        scene=scene,
        messages=messages,
        memory_filters=memory_filters,
        memory_limit=memory_limit,
        history_window=history_window,
    )
