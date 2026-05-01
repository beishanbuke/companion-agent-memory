from __future__ import annotations

from .types import ContextBlock, RouteResult
from .token_budget import estimate_tokens


def build_author_note(route: RouteResult) -> ContextBlock:
    if route.response_style == "comforting":
        style_rule = """\
- 先承认用户当前感受；
- 回复要短，不要讲大道理；
- 给一个非常小、马上能做的动作；
- 语气像同龄朋友，不像老师或医生。"""
    elif route.response_style == "structured":
        style_rule = """\
- 先给结论；
- 再给 3-5 个清晰步骤；
- 每一步要可执行；
- 避免空泛建议。"""
    elif route.response_style == "playful":
        style_rule = """\
- 可以轻松一点；
- 保持自然、有生活感；
- 不要过度正式。"""
    else:
        style_rule = """\
- 回复自然、简洁；
- 不要堆砌信息；
- 保持陪伴感。"""

    content = f"""\
[Post-History Instruction]
本轮用户意图：{route.intent}
用户情绪：{route.emotion}

回复约束：
{style_rule}

不要暴露你使用了哪些上下文模块，不要说"根据记忆显示"。""".strip()

    return ContextBlock(
        id="author_note:current_turn",
        type="author_note",
        role="system",
        title="Post-History Response Control",
        content=content,
        priority=96,
        tokens=estimate_tokens(content),
        required=True,
        source="author_note",
        reason="Placed near the end to control this specific response.",
        position="after_history",
    )
