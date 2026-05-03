"""Diet Advisor - 饮食建议

能力：
1. 饮食规律分析（基于用户历史）
2. 即时用餐建议（吃什么）
3. 饮食节奏修复（不规律改善）
4. 预算/热量粗估

不是营养师，是"懂吃的朋友"。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from prototype_demo.llm_client import get_llm_client


@dataclass
class DietAdvice:
    """饮食建议结果"""
    advice_type: str  # "meal_suggestion", "routine_fix", "budget_tips"
    main_advice: str  # 主要建议（自然语言）
    specific_options: list[dict[str, str]] = field(default_factory=list)  # 具体选项
    context_note: str = ""  # 给回复生成器的上下文提示
    confidence: float = 0.8


class DietAdvisor:
    """饮食建议器"""
    
    def __init__(self):
        self.llm = get_llm_client()
    
    async def suggest_meal(
        self,
        user_message: str,
        time_of_day: str = "",
        budget_hint: str = "",
        preference_hint: str = "",
        recent_meals: list[str] | None = None,
    ) -> DietAdvice:
        """建议吃什么"""
        
        recent = "\n".join([f"- {m}" for m in (recent_meals or [])[-5:]])
        
        prompt = f"""你是一个很懂吃的朋友，帮大学生决定吃什么。

用户消息：{user_message}
时间：{time_of_day or "未知"}
预算提示：{budget_hint or "未提及"}
偏好提示：{preference_hint or "未提及"}
最近饮食记录：
{recent or "无"}

请给出建议：
1. 主要推荐（1-2个具体选项，带店名/地点）
2. 备选（1个）
3. 为什么推荐这个（一句话）

要求：
- 像朋友推荐，不是美食博主
- 给出具体名字（"二食堂麻辣烫"而不是"麻辣烫"）
- 考虑时间和场景（早上不吃重口，晚上不推咖啡）
- 如果用户说"随便"，给一个明确的"就吃这个"

JSON 输出：
{{
    "main_advice": "主要建议（30字内）",
    "options": [
        {{"name": "选项名", "where": "在哪吃", "why": "推荐理由（15字内）", "price": "大概价格"}}
    ],
    "context_note": "给回复生成器的提示：该怎么跟用户说这个建议"
}}"""
        
        try:
            response = await self.llm.complete(prompt, max_tokens=300, temperature=0.7)
            cleaned = self._clean_json(response)
            result = json.loads(cleaned)
            
            return DietAdvice(
                advice_type="meal_suggestion",
                main_advice=result.get("main_advice", ""),
                specific_options=result.get("options", []),
                context_note=result.get("context_note", ""),
            )
        except Exception:
            # 降级
            return DietAdvice(
                advice_type="meal_suggestion",
                main_advice="食堂看看，或者你想吃什么我帮你挑",
                context_note="用户问吃什么，给轻松推荐",
            )
    
    async def fix_routine(
        self,
        user_message: str,
        routine_history: list[dict[str, Any]] | None = None,
    ) -> DietAdvice:
        """改善饮食不规律"""
        
        prompt = f"""用户说：{user_message}

你是一个朋友，不是营养师。用户饮食可能不规律（不吃早饭、乱吃、节食等）。

请给出建议：
1. 先理解用户现在的状况（不是批评）
2. 给一个小改变（这周只做一件事）
3. 给一个兜底方案（如果做不到怎么办）

要求：
- 不说"必须"
- 不说营养学大道理
- 具体：不说"吃早饭"，说"床头放包饼干"
- 允许退步："做不到也没关系，下周再说"

JSON 输出：
{{
    "main_advice": "核心建议（50字内）",
    "options": [
        {{"name": "小改变", "action": "具体做什么", "fallback": "做不到时的替代方案"}}
    ],
    "context_note": "回复语气提示"
}}"""
        
        try:
            response = await self.llm.complete(prompt, max_tokens=300, temperature=0.6)
            cleaned = self._clean_json(response)
            result = json.loads(cleaned)
            
            return DietAdvice(
                advice_type="routine_fix",
                main_advice=result.get("main_advice", ""),
                specific_options=result.get("options", []),
                context_note=result.get("context_note", ""),
            )
        except Exception:
            return DietAdvice(
                advice_type="routine_fix",
                main_advice="这周先试试吃早饭，做不到也没关系",
                context_note="温和建议饮食规律，不强迫",
            )
    
    def _clean_json(self, text: str) -> str:
        """清理 LLM 返回的 JSON"""
        cleaned = text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            if len(lines) > 2:
                cleaned = "\n".join(lines[1:-1])
            else:
                cleaned = cleaned.replace("```", "").replace("json", "")
        return cleaned.strip()
