from __future__ import annotations
from dataclasses import dataclass
from typing import Any


@dataclass
class ResponsePolicy:
    mode: str
    max_sentences: int = 5
    max_bullets: int = 3
    warmth: int = 2
    humor: int = 0
    action_size: str = "small"
    should_ask_question: bool = False
    forbidden_patterns: list[str] = None

    def to_prompt(self) -> str:
        forbidden = "、".join(self.forbidden_patterns or []) or "无"
        warmth_map = {
            0: "克制",
            1: "自然",
            2: "温和",
            3: "贴近但不过火",
        }
        humor_map = {
            0: "不刻意开玩笑",
            1: "可以有一点轻松感",
            2: "可以偶尔抖个小机灵",
        }
        bullet_rule = (
            f"如果必须列点，最多 {self.max_bullets} 条；"
            if self.max_bullets > 0
            else "这一轮不要列点；"
        )
        question_rule = (
            "只有在真的能推动对话时，最后再问一个轻一点的问题。"
            if self.should_ask_question
            else "这一轮不要为了显得会聊天而硬问问题。"
        )
        action_map = {
            "tiny": "给一个几乎不用思考就能做的小动作。",
            "small": "给一个具体、马上能执行的下一步。",
            "medium": "可以给一个短计划，但别铺太大。",
        }
        return f"""\
【本轮回复策略】
- 当前模式：{self.mode}
- 句子数尽量控制在 {self.max_sentences} 句以内。
- 语气要 {warmth_map.get(self.warmth, "自然")}，{humor_map.get(self.humor, "自然")}。
- {bullet_rule}
- {action_map.get(self.action_size, "优先给具体下一步。")}
- {question_rule}

表达要求：
- 先顺着用户当下的话头回，不要先做总结。
- 像真人聊天，不像模板助手；允许短句、半句、口语化表达。
- 如果用户只是吐槽/闲聊，就别强行上建议。
- 如果要提建议，先给结论或动作，不要先铺垫大道理。

禁止出现这些味道：{forbidden}
不要把自己写成客服、咨询师、老师或说明书。"""


def select_response_policy(signals: dict[str, Any], selected_skills: list[Any]) -> ResponsePolicy:
    mood = signals.get("mood")
    study = signals.get("study")
    food = signals.get("food")
    outfit = signals.get("outfit")
    music = signals.get("music")
    easter_eggs = signals.get("easter_eggs", [])

    if mood and mood.active and mood.data.get("subtype") == "tired":
        return ResponsePolicy(
            mode="low_battery",
            max_sentences=3,
            max_bullets=0,
            warmth=3,
            humor=0,
            action_size="tiny",
            should_ask_question=False,
            forbidden_patterns=[
                "长篇分析", "学习计划", "积极鸡汤", "你应该振作"
            ],
        )

    if study and study.active:
        return ResponsePolicy(
            mode="study_start",
            max_sentences=5,
            max_bullets=2,
            warmth=2,
            humor=0,
            action_size="tiny",
            should_ask_question=False,
            forbidden_patterns=[
                "完整时间表", "制定合理计划", "以下是一些建议", "SMART目标"
            ],
        )

    if food and food.active:
        return ResponsePolicy(
            mode="life_recommendation",
            max_sentences=5,
            max_bullets=3,
            warmth=1,
            humor=0,
            action_size="small",
            should_ask_question=False,
            forbidden_patterns=[
                "营养学长篇解释", "健康饮食很重要", "建议如下"
            ],
        )

    if outfit and outfit.active:
        return ResponsePolicy(
            mode="outfit_helper",
            max_sentences=5,
            max_bullets=3,
            warmth=1,
            humor=0,
            action_size="small",
            should_ask_question=False,
            forbidden_patterns=[
                "时尚博主口吻", "过度精致", "建议如下"
            ],
        )

    if music and music.active:
        return ResponsePolicy(
            mode="playlist_builder",
            max_sentences=5,
            max_bullets=3,
            warmth=1,
            humor=1,
            action_size="small",
            should_ask_question=False,
            forbidden_patterns=[
                "音乐理论", "百科式介绍", "以下是一些歌曲推荐"
            ],
        )

    if easter_eggs:
        return ResponsePolicy(
            mode="easter_egg",
            max_sentences=6,
            max_bullets=3,
            warmth=2,
            humor=1,
            action_size="small",
            should_ask_question=False,
            forbidden_patterns=[
                "过度表演", "尬梗", "长篇角色扮演"
            ],
        )

    return ResponsePolicy(
        mode="casual_chat",
        max_sentences=5,
        max_bullets=2,
        warmth=2,
        humor=1,
        action_size="small",
        should_ask_question=True,
        forbidden_patterns=[
            "客服腔", "心理咨询腔", "班主任腔", "正确废话"
        ],
    )
