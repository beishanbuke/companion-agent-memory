from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Signal:
    id: str
    type: str  # mood, food, music, outfit, campus, robot, easter_egg, lifestyle
    active: bool
    confidence: float = 0.0
    intent: str = ""
    data: dict[str, Any] = field(default_factory=dict)


def detect_mood(text: str) -> Signal:
    t = text.lower()
    
    # Low energy / tired
    if any(kw in t for kw in ["累", "困", "不想动", "没劲", "疲惫", " exhaustion", "tired", "exhausted", " drained"]):
        return Signal(
            id="mood_low_energy",
            type="mood",
            active=True,
            confidence=0.85,
            intent="low_battery_companion",
            data={"subtype": "tired", "response_length": "very_short"}
        )
    
    # Anxious / stressed
    if any(kw in t for kw in ["焦虑", "压力", "紧张", "害怕", "担心", "anxious", "stressed", "nervous", "worried"]):
        return Signal(
            id="mood_anxious",
            type="mood",
            active=True,
            confidence=0.85,
            intent="emotional_support",
            data={"subtype": "anxious"}
        )
    
    # Sad / down
    if any(kw in t for kw in ["难过", "伤心", "郁闷", "不开心", "sad", "upset", "depressed", "down", "blue", "难过", "烦", "烦死了"]):
        return Signal(
            id="mood_sad",
            type="mood",
            active=True,
            confidence=0.8,
            intent="emotional_support",
            data={"subtype": "sad"}
        )
    
    # Happy / energetic
    if any(kw in t for kw in ["开心", "兴奋", "开心", "happy", "excited", "great", "awesome"]):
        return Signal(
            id="mood_happy",
            type="mood",
            active=True,
            confidence=0.75,
            intent="casual_chat",
            data={"subtype": "happy"}
        )
    
    return Signal(
        id="mood_neutral",
        type="mood",
        active=False,
        confidence=0.5,
        intent="casual_chat",
        data={"subtype": "neutral"}
    )


def detect_food_intent(text: str) -> Signal:
    t = text.lower()
    
    # Diet routine / habit (check first for higher priority)
    diet_keywords = ["饮食", "饮食习惯", "不吃早饭", "乱吃", " diet", "eating habit", "meal plan"]
    if any(kw in t for kw in diet_keywords):
        return Signal(
            id="diet_routine_intent",
            type="food",
            active=True,
            confidence=0.8,
            intent="diet_routine",
            data={"subtype": "habit_fix"}
        )
    
    food_keywords = ["吃什么", "饿了", "晚饭", "午饭", "早饭", "早餐", "午餐", "晚餐", 
                     "外卖", "食堂", "奶茶", "火锅", "麻辣烫", "螺蛳粉", "面包", "粥",
                     "food", "hungry", "eat", "dinner", "lunch", "breakfast", "snack"]
    
    if any(kw in t for kw in food_keywords):
        # Detect specific food preferences
        spicy = any(kw in t for kw in ["辣", "麻辣", "spicy", "hot"])
        light = any(kw in t for kw in ["清淡", "轻", "简单", "light", "simple"])
        
        return Signal(
            id="food_intent",
            type="food",
            active=True,
            confidence=0.85,
            intent="food_recommendation",
            data={
                "spicy_preference": spicy,
                "light_preference": light,
                "time_of_day": "unknown"
            }
        )
    
    return Signal(
        id="food_none",
        type="food",
        active=False,
        confidence=0.0,
        intent="",
        data={}
    )


def detect_music_intent(text: str) -> Signal:
    t = text.lower()

    explicit_music_patterns = [
        r"想听(?:点|些)?(?:歌|音乐|歌单|摇滚|流行|爵士|民谣|说唱|rap|rock)",
        r"听点(?:歌|音乐|歌单|摇滚|流行|爵士|民谣|说唱|rap|rock)",
        r"来点(?:歌|音乐|歌单|摇滚|流行|爵士|民谣|说唱|rap|rock)",
        r"推荐(?:点|些)?(?:歌|音乐|歌单)",
        r"推(?:点|些)?歌",
    ]

    # Primary music keywords
    music_keywords = [
        "听歌", "音乐", " playlist", "song", "music", "推歌", "歌单",
        "曲子", "bgm", " soundtrack", "播放音乐", "放歌",
    ]

    # Band/artist/album keywords (broader music context)
    band_keywords = [
        "乐队", "band", "歌手", "artist", "音乐人", "组合", "乐团",
        "专辑", "album", "唱片", "ep", "单曲", "single",
        "演唱会", "concert", "live", "演出",
        "摇滚", "rock", "流行", "pop", "爵士", "jazz", "电子", "electronic",
        "说唱", "rap", "hip-hop", "民谣", "folk", "古典", "classic",
        " queen ", "beatles", "披头士", "beyond", "五月天", "周杰伦",
    ]

    has_explicit_music_pattern = any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in explicit_music_patterns)
    has_music_kw = has_explicit_music_pattern or any(kw in t for kw in music_keywords)
    has_band_kw = any(kw in t for kw in band_keywords)

    if has_music_kw or has_band_kw:
        # Detect mood for music
        low_energy = any(kw in t for kw in ["闷", "累", "安静", "chill", "relax", "calm", "soft", "轻"])
        energetic = any(kw in t for kw in ["嗨", "动", " upbeat", "energetic", "dance", "party"])

        # Check if it's asking about a specific band/artist
        asking_band = any(kw in t for kw in ["乐队", "band", "歌手", "artist", "是谁", "代表作", "经典"])

        # Detect music preference statements (e.g., "我喜欢摇滚乐")
        preference_patterns = [
            (r"喜欢(.*?)摇滚", "摇滚"),
            (r"喜欢(.*?)流行", "流行"),
            (r"喜欢(.*?)爵士", "爵士"),
            (r"喜欢(.*?)古典", "古典"),
            (r"喜欢(.*?)民谣", "民谣"),
            (r"喜欢(.*?)电子", "电子"),
            (r"喜欢(.*?)说唱", "说唱"),
            (r"爱听(.*?)摇滚", "摇滚"),
            (r"爱听(.*?)流行", "流行"),
            (r"常听(.*?)摇滚", "摇滚"),
            (r"常听(.*?)流行", "流行"),
        ]
        detected_preferences = []
        for pattern, genre in preference_patterns:
            if re.search(pattern, text):
                detected_preferences.append(genre)

        return Signal(
            id="music_intent",
            type="music",
            active=True,
            confidence=0.85 if has_music_kw else 0.75,
            intent="playlist_recommendation" if has_music_kw else "music_knowledge",
            data={
                "vibe": "low_energy" if low_energy else ("energetic" if energetic else "neutral"),
                "genre_hint": "",
                "asking_about_artist": asking_band,
                "detected_preferences": detected_preferences,
                "has_preference_statement": len(detected_preferences) > 0,
            }
        )

    return Signal(
        id="music_none",
        type="music",
        active=False,
        confidence=0.0,
        intent="",
        data={}
    )


def detect_outfit_intent(text: str) -> Signal:
    t = text.lower()
    
    outfit_keywords = ["穿什么", "穿搭", "衣服", "搭配", "outfit", "wear", "clothes", "dress", "穿啥", "出门穿", "穿得", "穿件", "穿个"]
    
    if any(kw in t for kw in outfit_keywords):
        # Detect scene
        formal = any(kw in t for kw in ["正式", "面试", "presentation", "formal", "interview", "重要"])
        casual = any(kw in t for kw in ["同学", "朋友", " casual", "日常", "随便"])
        
        return Signal(
            id="outfit_intent",
            type="outfit",
            active=True,
            confidence=0.85,
            intent="outfit_advice",
            data={
                "scene": "formal" if formal else ("casual" if casual else "unknown"),
                "weather_hint": ""
            }
        )
    
    return Signal(
        id="outfit_none",
        type="outfit",
        active=False,
        confidence=0.0,
        intent="",
        data={}
    )


def detect_campus_scene(text: str) -> Signal:
    t = text.lower()
    
    campus_keywords = ["图书馆", "教室", "宿舍", "食堂", "机房", "lab", "library", "classroom", "dorm"]
    
    if any(kw in t for kw in campus_keywords):
        # Detect specific location
        library = any(kw in t for kw in ["图书馆", "library"])
        lab = any(kw in t for kw in ["机房", "lab", "实验室", "服务器", "环境变量", "conda", "cuda"])
        dorm = any(kw in t for kw in ["宿舍", "dorm", "寝室"])
        
        return Signal(
            id="campus_scene",
            type="campus",
            active=True,
            confidence=0.8,
            intent="campus_place_suggestion",
            data={
                "location": "library" if library else ("lab" if lab else ("dorm" if dorm else "unknown")),
                "activity": "study" if library else ("coding" if lab else "rest")
            }
        )
    
    return Signal(
        id="campus_none",
        type="campus",
        active=False,
        confidence=0.0,
        intent="",
        data={}
    )


def detect_robot_affordance(text: str) -> Signal:
    t = text.lower()
    
    robot_keywords = ["机器人", "机械臂", "做个动作", "表情变化", "抱抱", "点点头", "语音播报", 
                      "robot", "gesture", "robotic", "embodied", "physical action", "movement"]
    
    if any(kw in t for kw in robot_keywords):
        return Signal(
            id="robot_affordance",
            type="robot",
            active=True,
            confidence=0.85,
            intent="robot_action",
            data={"action_type": "comfort"}
        )
    
    # Implicit robot need (when user is very tired or sad)
    implicit_signals = any(kw in t for kw in ["累死了", "不想说话", "好累", "烦死了", "so tired", "exhausted"])
    if implicit_signals:
        return Signal(
            id="robot_implicit",
            type="robot",
            active=True,
            confidence=0.6,
            intent="robot_action",
            data={"action_type": "gentle_support", "trigger": "implicit"}
        )
    
    return Signal(
        id="robot_none",
        type="robot",
        active=False,
        confidence=0.0,
        intent="",
        data={}
    )


def detect_easter_eggs(text: str) -> list[Signal]:
    t = text.lower()
    eggs: list[Signal] = []
    
    # Lab mode easter egg
    if any(kw in t for kw in ["机房", "环境变量", "conda", "cuda", "报错", "服务器", "跑代码", "debug", "bug"]):
        eggs.append(Signal(
            id="easter_egg_lab_mode",
            type="easter_egg",
            active=True,
            confidence=0.9,
            intent="lab_mode_easter_egg",
            data={"scene": "coding_lab", "fun_level": "high"}
        ))
    
    # Food fun mode
    if any(kw in t for kw in ["奶茶", "火锅", "麻辣烫", "螺蛳粉", "烧烤", "炸鸡"]):
        eggs.append(Signal(
            id="easter_egg_food_fun",
            type="easter_egg",
            active=True,
            confidence=0.75,
            intent="food_fun_mode",
            data={"food_type": "comfort_food", "fun_level": "medium"}
        ))
    
    # Youth slang mode
    if any(kw in t for kw in ["emo", "破防", "裂开", "摆烂", "躺平", "内卷", "yyds", "绝绝子", "社死", "牛马"]):
        eggs.append(Signal(
            id="easter_egg_youth_slang",
            type="easter_egg",
            active=True,
            confidence=0.8,
            intent="youth_slang_mode",
            data={"slang_detected": True, "fun_level": "medium"}
        ))
    
    return eggs


def detect_study_intent(text: str) -> Signal:
    t = text.lower()

    exam_keywords = [
        "考试", "期中", "期末", "quiz", "midterm", "final", "test",
        "复习", "刷题", "背书", "预习", "学不进去", "不会学"
    ]

    homework_keywords = [
        "作业", "ddl", "deadline", "presentation", "报告", "论文",
        "project", "汇报", "答辩"
    ]

    if any(kw in t for kw in exam_keywords):
        return Signal(
            id="exam_intent",
            type="study",
            active=True,
            confidence=0.9,
            intent="study_start",
            data={
                "subtype": "exam",
                "preferred_action_size": "tiny",
                "avoid_full_plan": True
            }
        )

    if any(kw in t for kw in homework_keywords):
        return Signal(
            id="study_task_intent",
            type="study",
            active=True,
            confidence=0.85,
            intent="study_task_support",
            data={
                "subtype": "task",
                "preferred_action_size": "small"
            }
        )

    return Signal(
        id="study_none",
        type="study",
        active=False,
        confidence=0.0,
        intent="",
        data={}
    )


def detect_all_signals(text: str) -> dict[str, Signal | list[Signal]]:
    """Run all detectors and return signals."""
    return {
        "mood": detect_mood(text),
        "study": detect_study_intent(text),
        "food": detect_food_intent(text),
        "music": detect_music_intent(text),
        "outfit": detect_outfit_intent(text),
        "campus": detect_campus_scene(text),
        "robot": detect_robot_affordance(text),
        "easter_eggs": detect_easter_eggs(text),
    }
