from __future__ import annotations

import re
from .types import RouteResult


def route_user_input(text: str) -> RouteResult:
    t = text.lower()

    intent: RouteResult.intent = "casual_chat"  # type: ignore[name-defined]
    emotion: RouteResult.emotion = "neutral"  # type: ignore[name-defined]
    skills: list[str] = []

    has_academic = bool(
        re.search(r"考试|作业|ddl|复习|课程|学习|presentation|midterm|final|quiz|homework", text, re.I)
    )

    has_emotion = bool(
        re.search(r"焦虑|烦|难受|崩溃|emo|不想学|学不进去|压力|累|失眠|睡不着", text, re.I)
    )

    has_plan = bool(
        re.search(r"计划|安排|怎么做|规划|schedule|plan|timeline|milestone", text, re.I)
    )

    has_robot = bool(
        re.search(r"机器人|动作|表情|陪我|抱抱|点头|语音|说话|robot|gesture|voice", text, re.I)
    )

    has_memory_recall = bool(
        re.search(r"还记得|我之前|上次|我的习惯|我喜欢|我讨厌|remember", text, re.I)
    )

    has_crisis = bool(
        re.search(r"不想活|自杀|伤害自己|结束生命|死了算了", text, re.I)
    )

    if has_crisis:
        return RouteResult(
            intent="crisis",
            emotion="sad",
            skills=["crisis_support"],
            need_memory=False,
            need_lorebook=False,
            need_robot_context=False,
            response_style="comforting",
        )

    if has_academic:
        intent = "academic_help"
        skills.append("study_plan")

    if has_emotion:
        if "烦" in t or "angry" in t:
            emotion = "angry"
        else:
            emotion = "anxious"
        skills.append("emotional_support")

    if has_plan:
        if intent == "casual_chat":
            intent = "planning"
        skills.append("planning")

    if has_robot:
        intent = "robot_action"
        skills.append("robot_action_mapping")

    if has_memory_recall:
        intent = "memory_recall"

    response_style = "short_warm"
    if has_emotion:
        response_style = "comforting"
    elif has_academic or has_plan:
        response_style = "structured"

    return RouteResult(
        intent=intent,
        emotion=emotion,
        skills=list(set(skills)),
        need_memory=has_memory_recall or has_academic or has_emotion or has_plan,
        need_lorebook=True,
        need_robot_context=has_robot,
        response_style=response_style,  # type: ignore[arg-type]
    )
