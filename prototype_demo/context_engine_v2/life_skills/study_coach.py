"""Study Coach - 学习规划

能力：
1. 考前微计划（3天/1周/当天）
2. 学习启动（学不进去时）
3. DDL 管理
4. 学习方法建议

不是学习博主，是"催你学习的室友"。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from prototype_demo.llm_client import get_llm_client


@dataclass
class StudyPlan:
    """学习计划结果"""
    plan_type: str  # "exam_prep", "task_breakdown", "motivation_boost"
    main_advice: str
    micro_steps: list[dict[str, Any]] = field(default_factory=list)
    time_estimate: str = ""
    context_note: str = ""
    confidence: float = 0.8


class StudyCoach:
    """学习教练"""
    
    def __init__(self):
        self.llm = get_llm_client()
    
    async def plan_exam_prep(
        self,
        user_message: str,
        exam_date: str = "",
        subject: str = "",
        current_status: str = "",
    ) -> StudyPlan:
        """考前规划"""
        
        prompt = f"""用户要考试了，你来帮ta规划。

用户消息：{user_message}
考试时间：{exam_date or "未知"}
科目：{subject or "未知"}
当前状态：{current_status or "未知"}

请给出一个"微计划"：
- 不要整周计划，只要"今天/接下来3小时做什么"
- 具体到动作："看第3章"而不是"复习"
- 给时间：每个动作多久
- 给优先级：如果只能做一件事，做哪个

要求：
- 像室友催学习，不是老师布置作业
- 允许完不成："做不完也没关系，做一点是一点"
- 如果用户很焦虑，先给"5分钟启动法"（只做5分钟）

JSON 输出：
{{
    "main_advice": "核心建议（40字内）",
    "micro_steps": [
        {{"action": "具体动作", "duration": "多久", "priority": "high|medium|low"}}
    ],
    "time_estimate": "总时间",
    "context_note": "回复语气提示"
}}"""
        
        try:
            response = await self.llm.complete(prompt, max_tokens=350, temperature=0.5)
            cleaned = self._clean_json(response)
            result = json.loads(cleaned)
            
            return StudyPlan(
                plan_type="exam_prep",
                main_advice=result.get("main_advice", ""),
                micro_steps=result.get("micro_steps", []),
                time_estimate=result.get("time_estimate", ""),
                context_note=result.get("context_note", ""),
            )
        except Exception:
            return StudyPlan(
                plan_type="exam_prep",
                main_advice="先打开书看5分钟，看完5分钟再说",
                micro_steps=[{"action": "看5分钟书", "duration": "5分钟", "priority": "high"}],
                context_note="轻松催学习，不制造焦虑",
            )
    
    async def help_start(
        self,
        user_message: str,
    ) -> StudyPlan:
        """学不进去时的启动帮助"""
        
        prompt = f"""用户说：{user_message}

ta学不进去。你不是要逼ta学，是要帮ta启动。

启动策略（选一个最适合的）：
1. 5分钟法：只学5分钟，5分钟后可以停
2. 换地法：离开宿舍去图书馆/咖啡厅
3. 组队法：找个同学一起学
4. 切割法：把任务切成极小的一块
5. 允许法：今天不学也行，但明天必须开始

请输出：
{{
    "main_advice": "给用户的建议（40字内，口语化）",
    "strategy": "用的策略名",
    "micro_steps": [{{"action": "", "duration": ""}}],
    "context_note": "怎么跟用户说这个建议"
}}"""
        
        try:
            response = await self.llm.complete(prompt, max_tokens=250, temperature=0.6)
            cleaned = self._clean_json(response)
            result = json.loads(cleaned)
            
            return StudyPlan(
                plan_type="motivation_boost",
                main_advice=result.get("main_advice", ""),
                micro_steps=result.get("micro_steps", []),
                context_note=result.get("context_note", ""),
            )
        except Exception:
            return StudyPlan(
                plan_type="motivation_boost",
                main_advice="别学了，先睡半小时。睡醒再说。",
                context_note="允许休息，不逼学习",
            )
    
    async def manage_deadline(
        self,
        user_message: str,
        tasks: list[dict[str, Any]] | None = None,
    ) -> StudyPlan:
        """DDL 管理"""
        
        tasks_str = ""
        if tasks:
            for t in tasks:
                tasks_str += f"- {t.get('name', '')}: 截止{t.get('deadline', '未知')}, 进度{t.get('progress', '未知')}\n"
        
        prompt = f"""用户有 DDL 压力。

用户消息：{user_message}
已知任务：
{tasks_str or "未提供"}

请帮ta排序和规划：
1. 哪个最急（不是最重要，是最急）
2. 今天必须做哪个
3. 哪个可以延期/水过去

要求：
- 直接给判断，不说"这取决于"
- 允许"水过去"：不是所有任务都要认真做
- 给具体时间："今晚8点前做完A"

JSON：
{{
    "main_advice": "核心判断",
    "micro_steps": [{{"action": "", "deadline": "", "can_water_down": true|false}}],
    "context_note": "语气提示"
}}"""
        
        try:
            response = await self.llm.complete(prompt, max_tokens=300, temperature=0.5)
            cleaned = self._clean_json(response)
            result = json.loads(cleaned)
            
            return StudyPlan(
                plan_type="task_breakdown",
                main_advice=result.get("main_advice", ""),
                micro_steps=result.get("micro_steps", []),
                context_note=result.get("context_note", ""),
            )
        except Exception:
            return StudyPlan(
                plan_type="task_breakdown",
                main_advice="先把最急的那个做了，其他的能水就水",
                context_note="轻松处理DDL，不制造焦虑",
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
