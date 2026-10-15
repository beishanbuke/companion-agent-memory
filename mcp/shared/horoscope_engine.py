"""Horoscope fortune engine for the companion agent.

Lightweight entertainment content: deterministic per (sign, date, theme),
no LLM required, stable within the same day. Style and emotion inputs only
adjust phrasing, never the underlying "prediction".
"""

from __future__ import annotations

import hashlib
import random
from datetime import date as date_type
from datetime import datetime


ZODIAC_SIGNS: dict[str, dict[str, object]] = {
    "aries": {"name": "白羊座", "symbol": "♈", "element": "火象", "keywords": "行动力 · 热情 · 直率"},
    "taurus": {"name": "金牛座", "symbol": "♉", "element": "土象", "keywords": "稳定 · 务实 · 耐心"},
    "gemini": {"name": "双子座", "symbol": "♊", "element": "风象", "keywords": "灵活 · 好奇 · 沟通"},
    "cancer": {"name": "巨蟹座", "symbol": "♋", "element": "水象", "keywords": "细腻 · 守护 · 共情"},
    "leo": {"name": "狮子座", "symbol": "♌", "element": "火象", "keywords": "自信 · 慷慨 · 表现力"},
    "virgo": {"name": "处女座", "symbol": "♍", "element": "土象", "keywords": "细致 · 条理 · 完美"},
    "libra": {"name": "天秤座", "symbol": "♎", "element": "风象", "keywords": "平衡 · 审美 · 和谐"},
    "scorpio": {"name": "天蝎座", "symbol": "♏", "element": "水象", "keywords": "专注 · 洞察 · 深沉"},
    "sagittarius": {"name": "射手座", "symbol": "♐", "element": "火象", "keywords": "自由 · 乐观 · 探索"},
    "capricorn": {"name": "摩羯座", "symbol": "♑", "element": "土象", "keywords": "自律 · 目标 · 坚韧"},
    "aquarius": {"name": "水瓶座", "symbol": "♒", "element": "风象", "keywords": "独立 · 创意 · 理性"},
    "pisces": {"name": "双鱼座", "symbol": "♓", "element": "水象", "keywords": "想象 · 温柔 · 直觉"},
}

# Aliases users might type
SIGN_ALIASES = {
    "白羊": "aries", "牡羊": "aries",
    "金牛": "taurus",
    "双子": "gemini",
    "巨蟹": "cancer",
    "狮子": "leo",
    "处女": "virgo", "室女": "virgo",
    "天秤": "libra", "天平": "libra",
    "天蝎": "scorpio",
    "射手": "sagittarius", "人马": "sagittarius",
    "摩羯": "capricorn", "山羊": "capricorn",
    "水瓶": "aquarius", "宝瓶": "aquarius",
    "双鱼": "pisces",
}

THEMES = {
    "general": "综合",
    "study": "学习工作",
    "love": "感情",
    "social": "社交",
    "health": "健康",
    "wealth": "财务",
}

THEME_ALIASES = {
    "study": ["学习", "考试", "复习", "功课", "作业", "工作", "任务", "项目", "面试", "汇报", "deadline", "DDL"],
    "love": ["感情", "恋爱", "桃花", "脱单", "暧昧", "表白", "暗恋", "复合", "分手", "对象", "喜欢的人"],
    "social": ["社交", "朋友", "人际", "聚会", "聊天", "认识", "相处", "同学", "同事"],
    "health": ["健康", "身体", "睡眠", "熬夜", "锻炼", "运动", "状态", "休息"],
    "wealth": ["财务", "钱", "理财", "消费", "花钱", "工资", "奖金", "投资", "省钱"],
}

STYLES = {"gentle": "温柔安抚", "cheerful": "活泼轻快", "calm": "稳重简洁"}

LUCKY_COLORS = [
    ("浅蓝色", "#7a9ab0"), ("奶杏色", "#d9b48f"), ("鼠尾草绿", "#8aaa8c"),
    ("雾粉色", "#d3a7b8"), ("鹅黄色", "#e3c766"), ("淡紫色", "#a58fc0"),
    ("珊瑚橙", "#d98a6a"), ("薄荷绿", "#8fc9b8"), ("燕麦白", "#e8dfd2"),
    ("玫瑰棕", "#b08a7a"), ("晴空蓝", "#6fa8d8"), ("暖沙色", "#cbb289"),
]

LUCKY_ACTIVITIES = [
    "整理桌面和文件夹", "散步十分钟", "听一张完整的专辑", "给自己泡一杯热饮",
    "写三行日记", "提前十分钟睡觉", "给老朋友发一条消息", "做一次深呼吸练习",
    "把待办清单拆成最小步骤", "抬头看看天空", "慢慢吃一顿饭", "收拾一个抽屉",
]

OVERALL_TEMPLATES = [
    "{sign}今天的节奏偏稳，适合把已经开了头的事情继续往前推一小步。",
    "{sign}今天容易在细节上找到手感，别急着求快，稳一点反而更快。",
    "{sign}今天的状态像慢热的火，开头有点钝，后面会越走越顺。",
    "{sign}今天适合先处理后沟通，把手里的事收尾会很有成就感。",
    "{sign}今天的灵感和执行力都在线，挑最重要的一件事先做。",
    "{sign}今天可能会遇到小插曲，但它们恰好能帮你调整节奏。",
    "{sign}今天的人际关系磁场不错，主动一点会有意外收获。",
    "{sign}今天适合做减法，删掉不必要的安排，留出缓冲。",
]

STUDY_ADVICE = [
    "适合推进沟通、写作和资料整理类任务，先把大纲搭起来。",
    "复杂任务适合拆小，先完成最容易开始的那一步。",
    "上午的思路比下午清晰，重要安排尽量往前放。",
    "今天适合复习和查漏补缺，新内容放到精力好的时段。",
    "容易被打断，给自己设一个 25 分钟的专注计时。",
    "适合向别人请教，一句提醒可能省下两小时。",
]

LOVE_ADVICE = [
    "表达欲比较强，适合主动联系在乎的人。",
    "适合倾听多于表达，对方可能正需要有人接住情绪。",
    "感情里的小误会适合今天说开，越拖越别扭。",
    "单身的人容易在自然场合遇到聊得来的人，不必刻意。",
    "适合安排一次轻松的见面，散步比正式约会更加分。",
]

SOCIAL_TIPS = [
    "社交运不错，适合参加轻松的聚会或群聊冒泡。",
    "今天容易成为别人的树洞，倾听也是加分项。",
    "适合修复一段有点疏远的关系，一句问候就够了。",
    "团队合作中少表态、多观察，你的稳重会被看见。",
    "今天的你自带亲和力，认识新朋友的好时机。",
]

HEALTH_TIPS = [
    "注意补水，久坐记得起来活动一下肩颈。",
    "今天精力起伏较大，重要事情放在状态好的时段。",
    "适合早睡半小时，身体会记住这份照顾。",
    "情绪容易影响胃口，吃饭尽量规律。",
]

WEALTH_TIPS = [
    "适合记账和复盘消费，容易发现可以优化的小地方。",
    "今天不适合冲动消费，先加购物车冷静一晚。",
    "正财稳定，如有额外进账可以考虑存下一部分。",
    "和朋友涉及金钱往来时，提前说清楚更省心。",
]

EMOTION_SOOTHING = {
    "焦虑": "感觉到你有点紧绷，先深呼吸——",
    "紧张": "别太绷着，给你一颗定心丸——",
    "疲惫": "辛苦啦，先允许自己慢半拍——",
    "累": "累了就先歇口气——",
    "低落": "抱抱你，今天的低潮是暂时的——",
    "难过": "先给你一个隔空拥抱——",
    "烦躁": "烦躁的时候最适合做点小小的整理——",
    "压力": "有压力说明你正在认真对待，先放轻松——",
}

EMOTION_CHEER = ["开心", "高兴", "兴奋", "期待", "愉快", "好"]

STYLE_OPENERS = {
    "gentle": "慢慢来啦，",
    "cheerful": "冲呀，",
    "calm": "按节奏走，",
}

SUMMARY_TEMPLATES = {
    "gentle": "今天不用急着做完美的决定，把小事做好就已经很棒了，我会一直在。",
    "cheerful": "今天的你自带光环，想做的事就大胆去试，好运站在行动派这边！",
    "calm": "运势只是参考，真正的节奏握在你手里，稳步推进就是今天的最优解。",
}

DISCLAIMER = "运势内容仅供娱乐参考，真正的选择在你自己手中。"

WEEKDAY_NAMES = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]


def normalize_sign(raw: str) -> str | None:
    """Map user input to a canonical zodiac key."""
    text = (raw or "").strip().lower()
    if not text:
        return None
    if text in ZODIAC_SIGNS:
        return text
    for alias, key in SIGN_ALIASES.items():
        if alias in text:
            return key
    return None


def extract_sign(message: str) -> str | None:
    """Find a zodiac sign mentioned in free text."""
    text = (message or "").lower()
    if not text:
        return None
    for alias, key in SIGN_ALIASES.items():
        if alias in text:
            return key
    for key in ZODIAC_SIGNS:
        if key in text:
            return key
    return None


def detect_theme(message: str) -> str:
    """Pick the most relevant theme from free text."""
    text = message or ""
    for theme, keywords in THEME_ALIASES.items():
        if any(k in text for k in keywords):
            return theme
    return "general"


def _parse_date(raw: str | None) -> date_type:
    if raw:
        try:
            return datetime.strptime(raw.strip(), "%Y-%m-%d").date()
        except ValueError:
            pass
    return date_type.today()


def _rng_for(sign: str, day: date_type, theme: str) -> random.Random:
    seed = f"{sign}|{day.isoformat()}|{theme}"
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return random.Random(int(digest[:16], 16))


def _pick_emotion_phrase(emotion: str) -> str:
    text = (emotion or "").strip()
    if not text:
        return ""
    for key, phrase in EMOTION_SOOTHING.items():
        if key in text:
            return phrase
    if any(word in text for word in EMOTION_CHEER):
        return "今天心情不错，正好借这股劲——"
    return ""


def generate_horoscope(
    sign: str,
    date: str | None = None,
    emotion: str = "",
    theme: str = "general",
    style: str = "gentle",
) -> dict[str, object]:
    """Generate a structured daily horoscope card."""
    key = normalize_sign(sign)
    if not key:
        raise ValueError(f"unknown zodiac sign: {sign!r}")

    day = _parse_date(date)
    theme_key = theme if theme in THEMES else detect_theme(theme or "")
    style_key = style if style in STYLES else "gentle"
    info = ZODIAC_SIGNS[key]
    rng = _rng_for(key, day, theme_key)

    overall_template = rng.choice(OVERALL_TEMPLATES)
    overall_fortune = overall_template.format(sign=info["name"])
    emotion_phrase = _pick_emotion_phrase(emotion)
    if emotion_phrase:
        overall_fortune = emotion_phrase + overall_fortune

    score = rng.randint(58, 96)
    if emotion_phrase and score < 70:
        score += 6  # keep soothing cards from feeling doom-y

    if theme_key == "love":
        advice = rng.choice(LOVE_ADVICE)
    elif theme_key == "social":
        advice = rng.choice(SOCIAL_TIPS)
    elif theme_key == "health":
        advice = rng.choice(HEALTH_TIPS)
    elif theme_key == "wealth":
        advice = rng.choice(WEALTH_TIPS)
    else:
        advice = rng.choice(STUDY_ADVICE)

    love_social = rng.choice(LOVE_ADVICE if theme_key != "love" else SOCIAL_TIPS)
    color_name, color_hex = rng.choice(LUCKY_COLORS)
    activity = rng.choice(LUCKY_ACTIVITIES)
    number = rng.randint(1, 9)
    opener = STYLE_OPENERS[style_key]
    summary = f"{opener}{SUMMARY_TEMPLATES[style_key]}"

    return {
        "sign": key,
        "sign_name": info["name"],
        "symbol": info["symbol"],
        "element": info["element"],
        "sign_keywords": info["keywords"],
        "image": f"/zodiac/{key}.jpg",
        "date": day.isoformat(),
        "weekday": WEEKDAY_NAMES[day.weekday()],
        "theme": theme_key,
        "theme_name": THEMES[theme_key],
        "emotion_input": (emotion or "").strip(),
        "style": style_key,
        "style_name": STYLES[style_key],
        "overall_score": score,
        "overall_fortune": overall_fortune,
        "advice": advice,
        "love_social_tips": love_social,
        "lucky_color": color_name,
        "lucky_color_hex": color_hex,
        "lucky_number": number,
        "lucky_activity": activity,
        "companion_summary": summary,
        "disclaimer": DISCLAIMER,
    }


def to_prompt_text(card: dict[str, object]) -> str:
    """Compact text used to inject the card into the chat prompt."""
    return (
        f"[星座运势 MCP 已生成 {card['sign_name']} {card['date']} 运势卡片]\n"
        f"整体运势 {card['overall_score']}%：{card['overall_fortune']}\n"
        f"{card['theme_name']}建议：{card['advice']}\n"
        f"感情社交：{card['love_social_tips']}\n"
        f"幸运色 {card['lucky_color']}、幸运数字 {card['lucky_number']}、"
        f"适合活动：{card['lucky_activity']}。\n"
        f"总结：{card['companion_summary']}\n"
        f"必须附带提醒：{card['disclaimer']}"
    )
