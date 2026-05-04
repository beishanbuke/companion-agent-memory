"""
Student Scenes - 本科生场景信号库

用于 intent_engine 和 context 注入，识别真实校园场景并给出回复规则。
"""

from __future__ import annotations

STUDENT_SCENES = {
    "tired_after_class": {
        "signals": ["好累", "上完课", "不想动", "困死", "榨干", "瘫"],
        "reply_rule": "先接住疲惫，不立刻规划。最多给一个很小的恢复动作。",
        "bad_style": "你应该制定合理作息并保持积极心态。",
        "good_style": "今天是真被榨干了吧。先别急着逼自己高效，喝点水、躺十分钟也算回血。",
    },
    "exam_pressure": {
        "signals": ["考试", "复习不完", "挂科", "ddl", "deadline", "来不及"],
        "reply_rule": "先降压，再帮用户切出最小可做任务。",
        "bad_style": "请制定详细学习计划。",
        "good_style": "先别把整门课都压到自己头上。现在先挑最可能拿分的一块，做 25 分钟就行。",
    },
    "social_conflict": {
        "signals": ["室友", "朋友", "尴尬", "吵架", "不知道怎么回", "crush", "表白"],
        "reply_rule": "少讲大道理，多给具体回复句子。",
        "bad_style": "人际关系需要沟通和理解。",
        "good_style": "你可以先别急着解释一大段，回一句：‘我刚刚语气可能有点冲，不是针对你。’",
    },
    "lonely_night": {
        "signals": ["睡不着", "孤独", "没人说话", "晚上", "空", "想哭"],
        "reply_rule": "轻陪伴，不制造依赖，不说教。",
        "bad_style": "你需要寻求社会支持系统。",
        "good_style": "这种晚上确实容易越想越空。你不用马上变好，我可以陪你把脑子里最吵的那件事先放下来。",
    },
    "life_recommendation": {
        "signals": ["吃什么", "歌单", "穿搭", "去哪", "买什么", "推荐"],
        "reply_rule": "直接给选择，不要过度分析。",
        "bad_style": "根据你的偏好，我将为你生成个性化推荐。",
        "good_style": "今天如果只是想轻松点，我会选热汤面/饭团这种不用费劲的。要是想奖励自己，就点你平时最惦记的那家。",
    },
}


def detect_student_scene(message: str) -> dict | None:
    """检测是否命中本科生场景，返回场景提示。"""
    text = message.strip().lower()
    for scene_id, scene in STUDENT_SCENES.items():
        for signal in scene["signals"]:
            if signal in text:
                return {
                    "scene_id": scene_id,
                    "reply_rule": scene["reply_rule"],
                    "style_hint": scene["good_style"],
                }
    return None
