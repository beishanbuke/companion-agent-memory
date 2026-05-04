"""
Situation Router

Classifies each user message into a situation category, then decides:
- Which memories to retrieve
- Which skills to activate
- Which MCP tools to call
- What response style to use
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any

import openai


@dataclass
class RoutingDecision:
    """Result of situation classification and routing."""
    situation: str
    confidence: float
    retrieve_memory: bool
    memory_tiers: list[str]  # Which tiers to retrieve
    activate_skills: list[str]
    call_tools: bool
    response_style: str
    safety_flag: bool


class SituationRouter:
    """Routes user messages to appropriate handling paths."""

    SITUATIONS = {
        "casual_chat": {
            "description": "普通聊天、日常问候、闲聊",
            "keywords": ["你好", "在吗", "干嘛", "聊", "hi", "hello", "what's up"],
            "retrieve_memory": True,
            "memory_tiers": ["profile", "preferences"],
            "skills": [],
            "call_tools": False,
            "style": "casual",
        },
        "emotional_support": {
            "description": "情绪陪伴、倾诉、安慰",
            "keywords": ["难过", "累", "烦", "焦虑", "压力", "sad", "tired", "stressed", "depressed", "worried"],
            "retrieve_memory": True,
            "memory_tiers": ["profile", "preferences", "episodic_events", "safety_notes"],
            "skills": ["emotional-companion"],
            "call_tools": False,
            "style": "empathetic",
        },
        "planning": {
            "description": "计划制定、任务安排、目标管理",
            "keywords": ["计划", "安排", "目标", "任务", "schedule", "plan", "goal", "task", "todo"],
            "retrieve_memory": True,
            "memory_tiers": ["profile", "long_term_goals", "episodic_events"],
            "skills": ["planning-helper"],
            "call_tools": False,
            "style": "structured",
        },
        "music_companion": {
            "description": "音乐推荐、播放、讨论",
            "keywords": ["歌", "音乐", "听", "推荐", "播放", "song", "music", "listen", "playlist", "artist"],
            "retrieve_memory": True,
            "memory_tiers": ["preferences"],
            "skills": ["music-dj"],
            "call_tools": True,
            "style": "enthusiastic",
        },
        "learning_coach": {
            "description": "学习辅导、知识问答、技能提升",
            "keywords": ["学", "教", "知识", "课程", "learn", "study", "teach", "course", "skill", "tutorial"],
            "retrieve_memory": True,
            "memory_tiers": ["profile", "preferences", "long_term_goals"],
            "skills": ["study-coach"],
            "call_tools": False,
            "style": "encouraging",
        },
        "coding_helper": {
            "description": "编程帮助、代码问题、技术讨论",
            "keywords": ["代码", "编程", "bug", "报错", "code", "programming", "python", "javascript", "error", "debug"],
            "retrieve_memory": True,
            "memory_tiers": ["profile", "preferences"],
            "skills": ["coding-helper"],
            "call_tools": True,
            "style": "technical",
        },
        "memory_query": {
            "description": "用户询问记忆、'你还记得吗'",
            "keywords": ["记得", "记住", "以前", "上次", "remember", "previously", "last time", "do you recall"],
            "retrieve_memory": True,
            "memory_tiers": ["profile", "preferences", "episodic_events", "long_term_goals"],
            "skills": ["memory-manager"],
            "call_tools": False,
            "style": "reminiscent",
        },
        "tool_task": {
            "description": "需要调用工具、查询信息",
            "keywords": ["查", "搜", "找", "搜索", "search", "look up", "find", "check", "query"],
            "retrieve_memory": True,
            "memory_tiers": ["profile"],
            "skills": ["tool-caller"],
            "call_tools": True,
            "style": "direct",
        },
        "safety_sensitive": {
            "description": "安全敏感场景、危机情况",
            "keywords": [
                "想死", "自杀", "自残", "伤害", "kill", "suicide", "self-harm",
                "hurt", "abuse", "violence", "crisis", "emergency",
            ],
            "retrieve_memory": True,
            "memory_tiers": ["safety_notes", "profile"],
            "skills": ["safety-handler"],
            "call_tools": False,
            "style": "supportive",
        },
        "personal_routine": {
            "description": "日常生活、习惯、健康",
            "keywords": ["习惯", "作息", "饮食", "运动", "sleep", "habit", "routine", "diet", "exercise"],
            "retrieve_memory": True,
            "memory_tiers": ["profile", "preferences", "episodic_events"],
            "skills": ["routine-tracker"],
            "call_tools": False,
            "style": "gentle",
        },
    }

    def __init__(self, model: str = "gpt-4o-mini"):
        self.model = model
        self._client = None
        self._init_client()

    def _init_client(self) -> None:
        """Initialize OpenAI client from environment."""
        api_key = os.getenv("OPENAI_API_KEY", "")
        base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        if api_key:
            self._client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url)

    async def classify(
        self,
        user_message: str,
        conversation_history: list[dict[str, str]] | None = None,
        use_llm: bool = False,
    ) -> RoutingDecision:
        """Classify user message into a situation.

        Uses fast keyword matching only. LLM fallback is disabled by default
        for speed. Set use_llm=True if you need nuanced classification.
        """
        # Fast path: keyword matching (always)
        situation, confidence = self._keyword_classify(user_message)

        # If confident enough, return immediately
        if confidence >= 0.8:
            return self._build_decision(situation, confidence)

        # LLM fallback only if explicitly enabled
        if use_llm and self._client and len(user_message) > 5:
            llm_situation, llm_confidence = await self._llm_classify(user_message, conversation_history)
            if llm_confidence > confidence:
                situation = llm_situation
                confidence = llm_confidence

        return self._build_decision(situation, confidence)

    def _keyword_classify(self, message: str) -> tuple[str, float]:
        """Classify based on keyword matching."""
        msg_lower = message.lower()
        scores = {}

        for situation, config in self.SITUATIONS.items():
            score = 0
            for keyword in config["keywords"]:
                if keyword in msg_lower:
                    score += 1
            if score > 0:
                scores[situation] = score

        if not scores:
            return "casual_chat", 0.3

        best = max(scores, key=scores.get)
        confidence = min(0.5 + scores[best] * 0.15, 0.9)
        return best, confidence

    async def _llm_classify(
        self,
        message: str,
        conversation_history: list[dict[str, str]] | None = None,
    ) -> tuple[str, float]:
        """Use LLM for nuanced classification."""
        history_context = ""
        if conversation_history:
            recent = conversation_history[-3:]
            history_context = "\n".join(
                f"{msg['role']}: {msg['content'][:100]}"
                for msg in recent
            )

        situations_desc = "\n".join(
            f"- {k}: {v['description']}"
            for k, v in self.SITUATIONS.items()
        )

        prompt = f"""请判断以下用户消息属于哪种情境。只输出 JSON。

可选情境：
{situations_desc}

最近的对话：
{history_context}

用户消息：{message!r}

请输出 JSON：
{{
  "situation": "情境名称",
  "confidence": 0.0-1.0,
  "reason": "简要说明"
}}"""

        try:
            response = await self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "你是一个情境分类助手，只输出 JSON。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                max_tokens=150,
            )
            content = response.choices[0].message.content or ""
            json_start = content.find("{")
            json_end = content.rfind("}")
            if json_start >= 0 and json_end > json_start:
                data = json.loads(content[json_start:json_end + 1])
                situation = data.get("situation", "casual_chat")
                confidence = float(data.get("confidence", 0.5))
                # Normalize situation name
                situation = situation.lower().replace(" ", "_").replace("-", "_")
                if situation not in self.SITUATIONS:
                    situation = "casual_chat"
                return situation, confidence
        except Exception:
            pass

        return "casual_chat", 0.3

    def _build_decision(self, situation: str, confidence: float) -> RoutingDecision:
        """Build routing decision from situation config."""
        config = self.SITUATIONS.get(situation, self.SITUATIONS["casual_chat"])

        # Safety override
        safety_flag = situation == "safety_sensitive"

        return RoutingDecision(
            situation=situation,
            confidence=confidence,
            retrieve_memory=config["retrieve_memory"],
            memory_tiers=config["memory_tiers"],
            activate_skills=config["skills"],
            call_tools=config["call_tools"],
            response_style=config["style"],
            safety_flag=safety_flag,
        )

    def get_situation_description(self, situation: str) -> str:
        """Get human-readable description of a situation."""
        config = self.SITUATIONS.get(situation)
        if config:
            return config["description"]
        return "未知情境"

    def get_all_situations(self) -> dict[str, str]:
        """Get all situation names and descriptions."""
        return {
            k: v["description"]
            for k, v in self.SITUATIONS.items()
        }
