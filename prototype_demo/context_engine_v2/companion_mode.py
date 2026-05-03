# LEGACY: companion_mode.py is deprecated. Use companion_agent/v2/ instead.
"""Companion Mode Router - 双脑模式判断器

判断当前轮次是"陪伴优先"还是"任务优先"，
决定后续走 chat mode（闲聊/情绪/接话）还是 task mode（学习/饮食/工具）。

不是规则匹配，是让 LLM 判断用户这轮到底想要什么。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from prototype_demo.llm_client import get_llm_client


@dataclass
class ModeDecision:
    """双脑模式决策结果"""
    primary_mode: str  # "chat" | "task" | "mixed"
    confidence: float
    user_intent: str  # 具体意图描述
    emotional_state: str  # 用户当前情绪状态
    suggested_tone: str  # 建议的回复语调
    context: dict[str, Any] = field(default_factory=dict)


# 轻规则兜底：明显的任务关键词直接走 task mode
_TASK_KEYWORDS = {
    "强任务": [
        "定外卖", "点外卖", "订餐", "下单",
        "查课表", "看课表", "今天有什么课",
        "设闹钟", "提醒我", "倒计时",
        "查成绩", "算绩点", "gpa",
        "算热量", "算卡路里", "计算",
        "生成", "制作", "创建",
    ],
    "学习任务": [
        "帮我规划", "制定计划", "复习计划",
        "考前", "备考", "突击",
        "论文", "报告", "ppt", "presentation",
    ],
    "生活任务": [
        "推荐吃的", "推荐餐厅", "附近有什么",
        "穿搭建议", "今天穿什么",
        "预算", "记账", "花了多少钱",
    ],
}

_CHAT_INDICATORS = [
    "哈哈哈", "哈哈", "笑死", "绝了", "牛逼", "卧槽",
    "烦死了", "好累", "不想动", "emo", "破防",
    "想你了", "在干嘛", "好无聊", "随便聊聊",
]


def _fast_path_check(text: str) -> ModeDecision | None:
    """快速路径：明显任务或明显闲聊直接返回，不走 LLM"""
    t = text.lower()
    
    # 强任务直接判 task
    for category, keywords in _TASK_KEYWORDS.items():
        if any(kw in t for kw in keywords):
            return ModeDecision(
                primary_mode="task",
                confidence=0.95,
                user_intent=f"明确{category}请求",
                emotional_state="neutral",
                suggested_tone=" friendly_helpful",
            )
    
    # 纯闲聊标记
    chat_score = sum(1 for ind in _CHAT_INDICATORS if ind in text)
    if chat_score >= 1 and len(text) < 30:
        return ModeDecision(
            primary_mode="chat",
            confidence=0.9,
            user_intent="随意闲聊/情绪抒发",
            emotional_state="casual",
            suggested_tone="relaxed_playful",
        )
    
    return None


async def decide_companion_mode(
    user_message: str,
    chat_history: list[dict[str, str]] | None = None,
    recent_mode: str = "chat",  # 上一轮的模式，保持连续性
) -> ModeDecision:
    """判断当前轮次应该以什么模式回应。
    
    流程：
    1. 快速路径检查（明显任务/闲聊）
    2. 用 LLM 做深度意图理解
    3. 结合上轮模式保持连续性
    """
    
    # 1. 快速路径
    fast = _fast_path_check(user_message)
    if fast:
        # 但如果上轮是 chat 且这轮很短，保持 chat
        if recent_mode == "chat" and len(user_message) < 15:
            fast.primary_mode = "chat"
            fast.confidence = 0.8
            fast.user_intent = "延续闲聊氛围"
        return fast
    
    # 2. LLM 深度判断
    llm = get_llm_client()
    
    history_str = ""
    if chat_history:
        recent = chat_history[-3:]
        for turn in recent:
            role = "用户" if turn.get("role") == "user" else "助手"
            history_str += f"{role}: {turn.get('content', '')}\n"
    
    prompt = f"""你是一个情境理解专家。请分析用户这条消息，判断最合适的回应模式。

【最近对话】
{history_str}
【用户当前消息】
{user_message}

【判断维度】
1. 用户这轮最想得到什么？（被陪伴/被逗笑/听建议/执行任务/安静待着）
2. 用户当前情绪状态？（开心/低落/焦虑/无聊/愤怒/平静/其他）
3. 这条消息更像"找人说话"还是"找人办事"？
4. 如果是混合意图，哪个更优先？

【模式定义】
- chat: 陪伴优先。接话、共情、玩梗、闲聊、情绪承接。不要给建议或执行工具。
- task: 任务优先。学习规划、饮食建议、穿搭推荐、工具调用。可以执行具体任务。
- mixed: 混合。先简短陪伴，再自然过渡到任务。

请用 JSON 格式输出（不要 markdown 代码块）：
{{
    "primary_mode": "chat|task|mixed",
    "confidence": 0.0-1.0,
    "user_intent": "具体描述用户想要什么",
    "emotional_state": "用户情绪",
    "suggested_tone": "建议语调（如：温柔陪伴/轻松调侃/认真建议/活力鼓励）",
    "reasoning": "判断理由，一句话"
}}"""

    try:
        response = await llm.complete(prompt, max_tokens=300, temperature=0.3)
        # 清理可能的 markdown 代码块
        cleaned = response.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1]
        if cleaned.endswith("```"):
            cleaned = cleaned.rsplit("\n", 1)[0]
        cleaned = cleaned.strip()
        
        result = json.loads(cleaned)
        
        mode = result.get("primary_mode", "chat")
        confidence = float(result.get("confidence", 0.7))
        
        # 连续性修正：如果上轮是 chat 且这轮 confidence 不高，保持 chat
        if recent_mode == "chat" and confidence < 0.75 and mode == "task":
            mode = "mixed"
            confidence = 0.6
        
        return ModeDecision(
            primary_mode=mode,
            confidence=confidence,
            user_intent=result.get("user_intent", ""),
            emotional_state=result.get("emotional_state", "neutral"),
            suggested_tone=result.get("suggested_tone", "natural"),
            context={"reasoning": result.get("reasoning", "")},
        )
    
    except Exception:
        # LLM 失败时，基于简单启发式兜底
        if any(kw in user_message for kw in ["？", "吗", "怎么", "什么", "哪", "建议"]):
            return ModeDecision(
                primary_mode="mixed",
                confidence=0.6,
                user_intent="询问/求助",
                emotional_state="neutral",
                suggested_tone="friendly_helpful",
            )
        else:
            return ModeDecision(
                primary_mode="chat",
                confidence=0.7,
                user_intent="日常交流",
                emotional_state="neutral",
                suggested_tone="natural",
            )
