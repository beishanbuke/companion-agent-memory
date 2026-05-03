# LEGACY: skills.py is deprecated. Use companion_agent/v2/ instead.
from __future__ import annotations

from .types import ContextBlock
from .token_budget import estimate_tokens


SKILL_PROMPTS: dict[str, str] = {
    "study_plan": """\
[Skill: Study Plan]
你要帮助用户把学习任务拆成很小、马上能开始的步骤。
优先输出：
1. 先共情一句；
2. 再给 15-25 分钟微计划；
3. 不要一次安排过满；
4. 用户焦虑时，不要批评拖延。
""",
    "emotional_support": """\
[Skill: Emotional Support]
你要温和、平等、自然地回应用户情绪。
规则：
- 先承认用户感受；
- 不要说教；
- 不要使用夸张鸡汤；
- 给一个很小的下一步动作；
- 语气像同龄朋友，不像心理医生。
""",
    "planning": """\
[Skill: Planning]
你要把模糊任务转成可执行计划。
输出格式：
- 当前目标
- 最近一步
- 30分钟行动
- 明天/本周安排
""",
    "robot_action_mapping": """\
[Skill: Robot Action Mapping]
当用户需要陪伴动作时，将回复拆成：
1. verbal_reply：自然语言回复；
2. robot_action：可执行动作，例如 nod, soft_light, smile_face, short_voice;
3. action_reason：为什么选择这个动作。
不要输出机器人无法执行的动作。
""",
    "crisis_support": """\
[Skill: Safety Support]
用户可能处于高风险状态时：
- 先表达关心；
- 鼓励联系身边可信任的人或当地紧急服务；
- 不要进行角色扮演；
- 不要给危险方法；
- 回复要简短、稳定、支持性强。
""",
}


def load_skill_blocks(skill_names: list[str]) -> list[ContextBlock]:
    blocks: list[ContextBlock] = []
    for name in skill_names:
        content = SKILL_PROMPTS.get(name, "").strip()
        if not content:
            continue
        blocks.append(
            ContextBlock(
                id=f"skill:{name}",
                type="skill",
                role="system",
                title=f"Skill: {name}",
                content=content,
                priority=84,
                tokens=estimate_tokens(content),
                source="skill_library",
                reason=f"Selected by Context Router: {name}",
                position="before_history",
            )
        )
    return blocks
