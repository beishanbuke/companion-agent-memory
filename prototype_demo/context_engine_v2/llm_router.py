# LEGACY: llm_router.py is deprecated. Use companion_agent/v2/ instead.
"""LLM Intent Router - 意图理解路由器

替代 signal_detectors.py 的 keyword 匹配，用 LLM 理解用户真实意图。
保留轻规则兜底作为 fast path。

输出不是"命中了哪个规则"，而是"用户这轮在什么状态、想要什么"。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from prototype_demo.llm_client import get_llm_client


@dataclass
class IntentUnderstanding:
    """用户意图理解结果"""
    # 核心意图（不是分类标签，是自然语言描述）
    intent_description: str
    
    # 情绪层
    emotional_state: str  # 开心/低落/焦虑/无聊/愤怒/平静/混合
    emotional_intensity: float  # 0-1
    
    # 关系层
    relationship_moment: str  # 这轮对话在关系中的定位
    # 例如："朋友吐槽日常"、"考前焦虑求助"、"无聊找存在感"、"试探性暧昧"
    
    # 行动层
    desired_action: str  # 用户希望发生什么
    # 例如："被倾听"、"被逗笑"、"给实用建议"、"一起吐槽"、"安静陪着"
    
    # 话题层
    topic_area: str  # food/study/music/social/emotion/campus/others
    
    # 隐式状态（连续性感知）
    implicit_state: str  # 用户当前处于什么连续状态
    # 例如："刚吐槽完还没消气"、"在撒娇"、"认真问事情"、"随口一提"
    
    # 原始数据
    confidence: float = 0.8
    raw_signals: dict[str, Any] = field(default_factory=dict)


# 轻规则兜底信号：作为 LLM 的参考输入，不作为决策依据
_LIGHT_SIGNALS = {
    "情绪": ["累", "困", "烦", "焦虑", "压力", "难过", "开心", "兴奋", "无聊", "emo", "破防"],
    "饮食": ["吃什么", "饿了", "外卖", "食堂", "奶茶", "火锅", "减肥", "热量"],
    "学习": ["考试", "复习", "作业", "ddl", "论文", "学不会", "备考", "挂科"],
    "社交": ["喜欢", "表白", "分手", "约会", "聊天", "朋友", "宿舍", "社死"],
    "音乐": ["听歌", "歌单", "推荐歌", "乐队", "演唱会"],
    "穿搭": ["穿什么", "穿搭", "衣服", "搭配"],
    "校园": ["图书馆", "教室", "宿舍", "食堂", "选课", "绩点"],
}


def _extract_light_signals(text: str) -> dict[str, list[str]]:
    """提取轻规则信号，只作为 LLM 的参考"""
    signals = {}
    for category, keywords in _LIGHT_SIGNALS.items():
        matched = [kw for kw in keywords if kw in text]
        if matched:
            signals[category] = matched
    return signals


async def understand_intent(
    user_message: str,
    chat_history: list[dict[str, str]] | None = None,
    memory_snippets: list[str] | None = None,
) -> IntentUnderstanding:
    """理解用户当前轮次的真实意图。
    
    这不是分类，是理解。输出应该是"用户在做什么"而不是"用户触发了哪个规则"。
    """
    
    llm = get_llm_client()
    
    # 构建上下文
    history_str = ""
    if chat_history:
        recent = chat_history[-5:]  # 最近 5 轮
        for turn in recent:
            role = "用户" if turn.get("role") == "user" else "你"
            content = turn.get("content", "")
            # 截断过长内容
            if len(content) > 100:
                content = content[:100] + "..."
            history_str += f"{role}: {content}\n"
    
    memory_str = ""
    if memory_snippets:
        memory_str = "\n".join([f"- {s}" for s in memory_snippets[:3]])
    
    light_signals = _extract_light_signals(user_message)
    signals_str = json.dumps(light_signals, ensure_ascii=False) if light_signals else "无明显关键词"
    
    prompt = f"""你是一个细腻的对话理解者。请深度理解用户这条消息，不只是看关键词，要看语境、语气、潜台词。

【关于用户】
{memory_str}

【最近对话】
{history_str}
【用户当前消息】
{user_message}

【参考信号（仅作提示，不要直接套用）】
{signals_str}

【理解要求】
1. 这条消息的"表面意思"和"真实需求"可能不同。比如"烦死了"可能不是要你解决什么，只是要人接一句"确实烦"
2. 注意语气和用词：用"哈哈哈"开场和用"那个"开场的情绪完全不同
3. 考虑连续性感知：用户是在延续之前的话题，还是在转移？是在回应你上句话，还是自说自话？
4. 判断"关系时刻"：这轮对话发生在什么关系情境中？（比如：朋友间吐槽、考前求助、深夜 emo、无聊找存在感）

请用 JSON 输出（不要 markdown 代码块）：
{{
    "intent_description": "一句话描述用户这轮到底想要什么（不是分类，是描述）",
    "emotional_state": "用户情绪状态",
    "emotional_intensity": 0.0-1.0,
    "relationship_moment": "这轮在关系中的定位",
    "desired_action": "用户希望你怎么回应",
    "topic_area": "food|study|music|social|emotion|campus|others",
    "implicit_state": "用户当前连续状态（如：刚吐槽完/在撒娇/认真问事/随口一提）",
    "confidence": 0.0-1.0
}}"""

    try:
        response = await llm.complete(prompt, max_tokens=400, temperature=0.3)
        
        # 清理 markdown
        cleaned = response.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            if len(lines) > 2:
                cleaned = "\n".join(lines[1:-1])
            else:
                cleaned = cleaned.replace("```", "").replace("json", "")
        cleaned = cleaned.strip()
        
        result = json.loads(cleaned)
        
        return IntentUnderstanding(
            intent_description=result.get("intent_description", "日常交流"),
            emotional_state=result.get("emotional_state", "neutral"),
            emotional_intensity=float(result.get("emotional_intensity", 0.5)),
            relationship_moment=result.get("relationship_moment", "普通对话"),
            desired_action=result.get("desired_action", "自然回应"),
            topic_area=result.get("topic_area", "others"),
            implicit_state=result.get("implicit_state", "随口一提"),
            confidence=float(result.get("confidence", 0.7)),
            raw_signals=light_signals,
        )
    
    except Exception:
        # 降级到轻规则
        topic = "others"
        for cat, kws in light_signals.items():
            if kws:
                topic_map = {
                    "情绪": "emotion",
                    "饮食": "food",
                    "学习": "study",
                    "社交": "social",
                    "音乐": "music",
                    "穿搭": "outfit",
                    "校园": "campus",
                }
                topic = topic_map.get(cat, "others")
                break
        
        return IntentUnderstanding(
            intent_description="基于关键词的意图推断（LLM 失败降级）",
            emotional_state="neutral",
            emotional_intensity=0.5,
            relationship_moment="普通对话",
            desired_action="自然回应",
            topic_area=topic,
            implicit_state="未知",
            confidence=0.4,
            raw_signals=light_signals,
        )
