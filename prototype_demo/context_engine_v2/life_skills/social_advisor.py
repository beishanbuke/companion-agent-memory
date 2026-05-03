"""Social Advisor - 社交/恋爱建议

能力：
1. 聊天回复建议（怎么回消息）
2. 邀约判断（要不要约、怎么约）
3. 边界感建议（室友/朋友/恋人关系）
4. 社交疲惫处理

不是情感博主，是"帮你分析的朋友"。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from prototype_demo.llm_client import get_llm_client


@dataclass
class SocialAdvice:
    """社交建议结果"""
    advice_type: str  # "chat_reply", "date_advice", "boundary", "social_fatigue"
    main_advice: str
    specific_tips: list[str] = field(default_factory=list)
    red_flags: list[str] = field(default_factory=list)
    context_note: str = ""
    confidence: float = 0.8


class SocialAdvisor:
    """社交建议器"""
    
    def __init__(self):
        self.llm = get_llm_client()
    
    async def suggest_reply(
        self,
        user_message: str,
        chat_screenshot: str = "",  # 用户提供的聊天内容
        relationship: str = "",  # 关系：朋友/暧昧/恋人/室友
    ) -> SocialAdvice:
        """建议怎么回复消息"""
        
        prompt = f"""用户不知道怎么回复一条消息，你来帮ta。

关系：{relationship or "未说明"}
用户描述：{user_message}
聊天内容：{chat_screenshot or "未提供具体内容"}

请给出建议：
1. 分析对方消息的真实意图（不是表面意思）
2. 给出 2 个回复选项：
   - 选项A：安全/稳妥的
   - 选项B：推进关系的（如果适用）
3. 每个选项附带"可能的结果"和"风险"

要求：
- 不说"真诚最重要"这种废话
- 给具体文字："你可以说：'xxx'"
- 考虑关系阶段：暧昧期、朋友期、恋人期策略不同
- 如果对方消息有 red flag，指出来

JSON：
{{
    "main_advice": "整体判断",
    "specific_tips": [
        "选项A：具体回复文字",
        "选项B：具体回复文字"
    ],
    "red_flags": ["如果有问题，列出来"],
    "context_note": "怎么跟用户说这个建议"
}}"""
        
        try:
            response = await self.llm.complete(prompt, max_tokens=400, temperature=0.6)
            cleaned = self._clean_json(response)
            result = json.loads(cleaned)
            
            return SocialAdvice(
                advice_type="chat_reply",
                main_advice=result.get("main_advice", ""),
                specific_tips=result.get("specific_tips", []),
                red_flags=result.get("red_flags", []),
                context_note=result.get("context_note", ""),
            )
        except Exception:
            return SocialAdvice(
                advice_type="chat_reply",
                main_advice="不知道怎么回就先不回，等想好了再说",
                specific_tips=["先发个表情包拖一下", "或者直接问'你什么意思'"],
                context_note="给轻松建议，不制造社交焦虑",
            )
    
    async def date_advice(
        self,
        user_message: str,
        relationship_stage: str = "",  # 未表白/暧昧/刚在一起/稳定
    ) -> SocialAdvice:
        """邀约建议"""
        
        prompt = f"""用户在考虑要不要约人/怎么约人。

关系阶段：{relationship_stage or "未知"}
用户想法：{user_message}

请分析：
1. 现在的时机合适吗？
2. 如果约，用什么理由/方式最自然？
3. 如果被拒，怎么给自己台阶下？

要求：
- 给具体方案："周五晚上说'新开了家店，一起去？'"
- 考虑被拒绝的场景，给用户留后路
- 不说"勇敢去"，说"这样约最自然"

JSON：
{{
    "main_advice": "时机判断+建议",
    "specific_tips": ["具体邀约方式", "备选方案"],
    "red_flags": ["可能的问题"],
    "context_note": "语气提示"
}}"""
        
        try:
            response = await self.llm.complete(prompt, max_tokens=300, temperature=0.6)
            cleaned = self._clean_json(response)
            result = json.loads(cleaned)
            
            return SocialAdvice(
                advice_type="date_advice",
                main_advice=result.get("main_advice", ""),
                specific_tips=result.get("specific_tips", []),
                red_flags=result.get("red_flags", []),
                context_note=result.get("context_note", ""),
            )
        except Exception:
            return SocialAdvice(
                advice_type="date_advice",
                main_advice="想约就约，但找个具体理由，别直接说'出去玩'",
                specific_tips=["用具体事由：新电影/新餐厅/作业讨论"],
                context_note="给具体建议，不打鸡血",
            )
    
    async def boundary_advice(
        self,
        user_message: str,
        relationship_type: str = "",  # 室友/朋友/恋人/同学
    ) -> SocialAdvice:
        """边界感建议"""
        
        prompt = f"""用户在一段关系中感到不舒服，可能是边界被侵犯了。

关系类型：{relationship_type or "未知"}
用户描述：{user_message}

请给出建议：
1. 判断：这是正常的摩擦，还是确实越界了？
2. 如果越界：怎么温和但明确地表达边界？
3. 给具体话术："你可以说：'xxx'"
4. 如果对方不改，下一步怎么办？

要求：
- 不劝"忍一忍"
- 不给"直接绝交"这种极端建议
- 给渐进式策略：先暗示→再明确→最后远离

JSON：
{{
    "main_advice": "核心判断",
    "specific_tips": ["话术1", "话术2"],
    "red_flags": ["如果这样就是red flag"],
    "context_note": "语气提示"
}}"""
        
        try:
            response = await self.llm.complete(prompt, max_tokens=350, temperature=0.5)
            cleaned = self._clean_json(response)
            result = json.loads(cleaned)
            
            return SocialAdvice(
                advice_type="boundary",
                main_advice=result.get("main_advice", ""),
                specific_tips=result.get("specific_tips", []),
                red_flags=result.get("red_flags", []),
                context_note=result.get("context_note", ""),
            )
        except Exception:
            return SocialAdvice(
                advice_type="boundary",
                main_advice="不舒服就说，不用忍着",
                specific_tips=["直接说：'你这样我不太舒服'", "不用解释太多"],
                context_note="支持用户设立边界",
            )
    
    def _clean_json(self, text: str) -> str:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            if len(lines) > 2:
                cleaned = "\n".join(lines[1:-1])
            else:
                cleaned = cleaned.replace("```", "").replace("json", "")
        return cleaned.strip()
