"""
Skill Registry

Manages skills that can be activated based on situation routing.
Skills are organized into tiers:
- Tier 1 (Built-in): Always available, core companion capabilities
- Tier 2 (Domain): Situation-specific skills
- Tier 3 (External): MCP-connected skills

A skill is a callable that receives context and returns a result.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable


@dataclass
class Skill:
    """Definition of a skill."""
    name: str
    description: str
    tier: int  # 1=built-in, 2=domain, 3=external
    situations: list[str]  # Which situations can trigger this skill
    handler: Callable[..., Awaitable[Any]] | None = None
    requires_mcp: bool = False
    mcp_tools: list[str] = field(default_factory=list)


class SkillRegistry:
    """Registry and executor for skills."""

    def __init__(self):
        self._skills: dict[str, Skill] = {}
        self._register_builtin_skills()

    def _register_builtin_skills(self) -> None:
        """Register built-in Tier 1 skills."""
        self.register(Skill(
            name="emotional-companion",
            description="提供情绪支持和共情回应",
            tier=1,
            situations=["emotional_support", "safety_sensitive"],
        ))
        self.register(Skill(
            name="memory-manager",
            description="帮助用户查看、修改、删除记忆",
            tier=1,
            situations=["memory_query"],
        ))
        self.register(Skill(
            name="safety-handler",
            description="处理安全敏感场景，提供危机支持",
            tier=1,
            situations=["safety_sensitive"],
        ))
        self.register(Skill(
            name="planning-helper",
            description="帮助用户制定计划和拆解任务",
            tier=2,
            situations=["planning"],
        ))
        self.register(Skill(
            name="music-dj",
            description="音乐推荐和播放控制",
            tier=2,
            situations=["music_companion"],
            requires_mcp=True,
            mcp_tools=["radio_dj.create_playlist", "radio_dj.get_artist_info", "radio_dj.suggest_music_for_scene", "radio_dj.play_track"],
        ))
        self.register(Skill(
            name="study-coach",
            description="学习辅导和知识解释",
            tier=2,
            situations=["learning_coach"],
        ))
        self.register(Skill(
            name="coding-helper",
            description="编程帮助和代码解释",
            tier=2,
            situations=["coding_helper"],
        ))
        self.register(Skill(
            name="tool-caller",
            description="调用外部工具获取信息",
            tier=2,
            situations=["tool_task"],
            requires_mcp=True,
        ))
        self.register(Skill(
            name="routine-tracker",
            description="跟踪日常生活习惯",
            tier=2,
            situations=["personal_routine"],
        ))

    def register(self, skill: Skill) -> None:
        """Register a new skill."""
        self._skills[skill.name] = skill

    def resolve(self, situation: str) -> list[Skill]:
        """Get skills activated for a situation."""
        return [
            skill for skill in self._skills.values()
            if situation in skill.situations
        ]

    def get_skill(self, name: str) -> Skill | None:
        """Get a skill by name."""
        return self._skills.get(name)

    def list_skills(self, tier: int | None = None) -> list[Skill]:
        """List all skills, optionally filtered by tier."""
        if tier is None:
            return list(self._skills.values())
        return [s for s in self._skills.values() if s.tier == tier]

    async def execute(
        self,
        skill_name: str,
        context: dict[str, Any],
    ) -> Any:
        """Execute a skill with given context."""
        skill = self._skills.get(skill_name)
        if not skill:
            return {"error": f"Skill '{skill_name}' not found"}

        if skill.handler:
            return await skill.handler(context)

        # Default: return skill info as placeholder
        return {
            "skill": skill_name,
            "status": "activated",
            "description": skill.description,
        }

    def get_skill_descriptions(self) -> dict[str, str]:
        """Get all skill names and descriptions."""
        return {
            name: skill.description
            for name, skill in self._skills.items()
        }
