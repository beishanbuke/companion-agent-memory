from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


@dataclass
class SkillManifest:
    id: str
    name: str
    category: Literal[
        "music", "outfit", "food", "diet_plan", "campus_life",
        "easter_egg", "study", "emotion", "robot", "general"
    ]
    triggers: list[str]
    required_signals: list[str]
    activation_mode: Literal["explicit", "implicit", "easter_egg"]
    context_policy: dict[str, Any]
    output_mode: Literal[
        "chat", "structured_card", "robot_action",
        "playlist_card", "food_card", "outfit_card", "diet_plan_card"
    ]
    system_prompt: str = ""
    max_tokens: int = 200


SKILL_MANIFESTS: list[SkillManifest] = [
    SkillManifest(
        id="playlist_builder",
        name="定制歌单",
        category="music",
        triggers=["music_intent"],
        required_signals=["music"],
        activation_mode="explicit",
        context_policy={
            "max_tokens": 150,
            "inject_user_memory": False,
            "inject_recent_state": True,
            "ask_before_acting": False,
        },
        output_mode="playlist_card",
        system_prompt="""\
你是一个音乐推荐助手。用户想听歌。
规则：
- 不要输出一大段音乐理论
- 给 3-5 首歌的 vibe 描述
- 按场景/心情分组
- 总回复控制在 100 字内""",
        max_tokens=150,
    ),
    
    SkillManifest(
        id="outfit_helper",
        name="穿搭建议",
        category="outfit",
        triggers=["outfit_intent"],
        required_signals=["outfit"],
        activation_mode="explicit",
        context_policy={
            "max_tokens": 150,
            "inject_user_memory": False,
            "inject_recent_state": False,
            "ask_before_acting": False,
        },
        output_mode="outfit_card",
        system_prompt="""\
你给一个大学生提供穿搭建议。
规则：
- 实用为主，不追求潮流
- 全身不超过 3 个颜色
- 给出具体单品（卫衣/衬衫/裤子/鞋）
- 控制在 80 字内""",
        max_tokens=150,
    ),
    
    SkillManifest(
        id="food_picker",
        name="美食推荐",
        category="food",
        triggers=["food_intent"],
        required_signals=["food"],
        activation_mode="explicit",
        context_policy={
            "max_tokens": 120,
            "inject_user_memory": True,
            "inject_recent_state": True,
            "ask_before_acting": False,
        },
        output_mode="food_card",
        system_prompt="""\
你帮用户决定吃什么。
规则：
- 给 2-3 个具体选项（面/饭/粉等）
- 考虑时间和饱腹感
- 不要推荐具体餐厅
- 控制在 80 字内""",
        max_tokens=120,
    ),
    
    SkillManifest(
        id="diet_routine",
        name="饮食节奏修复",
        category="diet_plan",
        triggers=["diet_routine_intent"],
        required_signals=["food"],
        activation_mode="explicit",
        context_policy={
            "max_tokens": 200,
            "inject_user_memory": True,
            "inject_recent_state": True,
            "ask_before_acting": False,
        },
        output_mode="diet_plan_card",
        system_prompt="""\
你帮用户建立不痛苦的饮食习惯。
规则：
- 不搞健身博主那套
- 每天只抓 1-2 件事
- 第一周目标：别乱到失控
- 语气像朋友，不是营养师
- 控制在 120 字内""",
        max_tokens=200,
    ),
    
    SkillManifest(
        id="campus_place_suggestion",
        name="校园地点推荐",
        category="campus_life",
        triggers=["campus_scene"],
        required_signals=["campus"],
        activation_mode="implicit",
        context_policy={
            "max_tokens": 120,
            "inject_user_memory": False,
            "inject_recent_state": False,
            "ask_before_acting": False,
        },
        output_mode="chat",
        system_prompt="""\
你推荐校园里的学习/休息地点。
规则：
- 给出 2-3 个具体地点
- 说明每个地点适合做什么
- 不要只推图书馆
- 控制在 80 字内""",
        max_tokens=120,
    ),
    
    SkillManifest(
        id="lab_mode_easter_egg",
        name="机房彩蛋",
        category="easter_egg",
        triggers=["easter_egg_lab_mode"],
        required_signals=["easter_eggs"],
        activation_mode="easter_egg",
        context_policy={
            "max_tokens": 150,
            "inject_user_memory": False,
            "inject_recent_state": False,
            "ask_before_acting": False,
        },
        output_mode="chat",
        system_prompt="""\
你切换到机房陪伴模式。
规则：
- 轻松幽默
- 可以调侃环境变量、bug、conda
- 给出实际建议：先跑起来，再看报错
- 像懂编程的朋友，不是老师
- 控制在 100 字内""",
        max_tokens=150,
    ),
    
    SkillManifest(
        id="low_battery_companion",
        name="低电量陪伴",
        category="emotion",
        triggers=["mood_low_energy"],
        required_signals=["mood"],
        activation_mode="implicit",
        context_policy={
            "max_tokens": 80,
            "inject_user_memory": False,
            "inject_recent_state": True,
            "ask_before_acting": False,
        },
        output_mode="chat",
        system_prompt="""\
用户很累/不想说话。你的回复应该：
- 非常短（30-50 字）
- 不逼他们说话
- 安静陪伴
- 给一个小动作建议（喝水/躺下/关灯）
- 像室友，不是心理咨询师""",
        max_tokens=80,
    ),
    
    SkillManifest(
        id="study_micro_planner",
        name="学习微计划",
        category="study",
        triggers=["study_intent", "exam_intent"],
        required_signals=["mood", "campus"],
        activation_mode="implicit",
        context_policy={
            "max_tokens": 120,
            "inject_user_memory": True,
            "inject_recent_state": True,
            "ask_before_acting": False,
        },
        output_mode="chat",
        system_prompt="""\
你帮用户做很小的学习计划。
规则：
- 先共情一句
- 给 15-25 分钟微计划
- 一次只做一件事
- 不批评拖延
- 控制在 80 字内""",
        max_tokens=120,
    ),
    
    SkillManifest(
        id="robot_action",
        name="机器人动作",
        category="robot",
        triggers=["robot_affordance"],
        required_signals=["robot"],
        activation_mode="explicit",
        context_policy={
            "max_tokens": 100,
            "inject_user_memory": False,
            "inject_recent_state": False,
            "ask_before_acting": False,
        },
        output_mode="robot_action",
        system_prompt="""\
用户需要机器人动作。输出格式：
1. verbal_reply：自然语言回复
2. robot_action：具体动作（nod/soft_light/smile_face/short_voice）
3. action_reason：为什么选这个动作
不要承诺无法执行的动作。""",
        max_tokens=100,
    ),
    
    SkillManifest(
        id="radio_dj",
        name="电台DJ",
        category="music",
        triggers=["music_intent", "band_knowledge", "playlist_request"],
        required_signals=["music"],
        activation_mode="explicit",
        context_policy={
            "max_tokens": 200,
            "inject_user_memory": True,
            "inject_recent_state": True,
            "ask_before_acting": False,
        },
        output_mode="playlist_card",
        system_prompt="""\
你是用户的私人电台DJ，根据用户的场景、心情和偏好创作歌单。

规则：
- 每次推荐 3-5 首歌
- 给出 DJ 风格的介绍语（20-30 字）
- 如果用户提到具体乐队/歌手，优先推荐该艺人的歌
- 结合用户当前场景（南沙、港科大广州、学习等）做本地化推荐
- 控制在 100 字内
- 可用 MCP 工具：radio_dj.create_playlist, radio_dj.get_artist_info, radio_dj.suggest_music_for_scene""",
        max_tokens=200,
    ),
]


def select_skills(
    signals: dict[str, Any],
    max_skills: int = 2,
) -> list[tuple[SkillManifest, str, float]]:
    """Select skills based on signals.
    
    Returns list of (skill, mode, score) where mode is 'primary', 'support', or 'background'.
    """
    candidates = []
    
    for skill in SKILL_MANIFESTS:
        score = 0.0
        matched_signals = []
        trigger_matched = False
        
        # Check required signals AND triggers
        for req_signal in skill.required_signals:
            signal = signals.get(req_signal)
            if signal:
                if isinstance(signal, list):
                    # easter_eggs is a list
                    for s in signal:
                        if s.active:
                            # Check if any trigger matches
                            if any(t in s.id for t in skill.triggers):
                                score += s.confidence
                                matched_signals.append(s.id)
                                trigger_matched = True
                elif signal.active:
                    # Check if signal id or intent matches any trigger
                    if any(t in signal.id or t in signal.intent for t in skill.triggers):
                        score += signal.confidence
                        matched_signals.append(signal.id)
                        trigger_matched = True
        
        # Only consider skill if at least one trigger matched
        if trigger_matched and score > 0.3:
            # Determine mode based on score and activation_mode
            if skill.activation_mode == "explicit" and score >= 0.7:
                mode = "primary"
            elif skill.activation_mode == "easter_egg" and score >= 0.7:
                mode = "primary"
            elif score >= 0.6:
                mode = "support"
            else:
                mode = "background"
            
            candidates.append((skill, mode, score))
    
    # Sort by score
    candidates.sort(key=lambda x: x[2], reverse=True)
    
    # Deduplicate by category: keep only the highest-scored skill per category
    # for primary/support modes. Background skills are allowed to overlap.
    category_primary_support: dict[str, tuple[SkillManifest, str, float]] = {}
    background_candidates = []
    for skill, mode, score in candidates:
        if mode == "background":
            background_candidates.append((skill, mode, score))
        else:
            existing = category_primary_support.get(skill.category)
            if existing is None or score > existing[2]:
                category_primary_support[skill.category] = (skill, mode, score)

    deduped = list(category_primary_support.values())
    deduped.sort(key=lambda x: x[2], reverse=True)

    # Allow background skills to fill remaining slots
    result = deduped[:max_skills]
    if len(result) < max_skills:
        result.extend(background_candidates[: max_skills - len(result)])

    return result


def get_skill_by_id(skill_id: str) -> SkillManifest | None:
    for skill in SKILL_MANIFESTS:
        if skill.id == skill_id:
            return skill
    return None
