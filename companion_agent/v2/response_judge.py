"""
Response Judge v2

回复后评审系统（使用统一 LLM Runtime）：
每轮生成回复后，做一次轻评估：
- 有没有模板味
- 有没有说教
- 有没有误触发任务模式
- 有没有问了不该问的问题
- 角色一致性检查

分级重写：
- 轻问题：只改语气，不改语义（tone_fix）
- 重问题：整句重写（rewrite）

记录"为什么被打回"，形成 prompt 调优闭环。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .llm_runtime import get_llm_runtime, LLMRuntime


@dataclass
class JudgeResult:
    """评审结果。"""
    is_good: bool
    score: float  # 0-10
    issues: list[str]
    suggestions: list[str]
    improved_reply: str
    rewrite_level: str  # "none" / "tone_fix" / "rewrite"
    rewrite_reason: str  # 为什么需要重写


class ResponseJudge:
    """回复质量评审器（统一 Runtime）。"""
    
    TEMPLATE_PATTERNS = [
        "以下是", "建议您", "首先", "其次", "最后", "总结", "综上所述",
        "针对您的问题", "根据您的描述", "希望以上", "如有需要",
    ]
    
    PREACHY_PATTERNS = [
        "你应该", "你需要", "你必须", "重要的是", "记住要",
        "不要忘记", "关键在于", "本质上", "其实你应该",
    ]
    
    SERVICE_PATTERNS = [
        "很高兴", "为您服务", "请问还有什么", "感谢您的", "祝您", "欢迎",
    ]
    
    def __init__(self, runtime: LLMRuntime | None = None):
        self._runtime = runtime or get_llm_runtime()
        self._rejection_history: list[dict[str, Any]] = []  # 记录打回原因，形成闭环
    
    async def judge(
        self,
        user_message: str,
        assistant_reply: str,
        conversation_mode: str = "chat",
        conversation_state: dict[str, Any] | None = None,
    ) -> JudgeResult:
        """评审回复质量，分级重写。"""
        
        issues = []
        
        # === 规则层检测 ===
        issues.extend(self._check_template_smell(assistant_reply))
        issues.extend(self._check_preachy(assistant_reply))
        issues.extend(self._check_service_tone(assistant_reply))
        issues.extend(self._check_wrong_mode(assistant_reply, conversation_mode))
        issues.extend(self._check_bad_questions(assistant_reply))
        issues.extend(self._check_parentheses(assistant_reply))
        issues.extend(self._check_self_reference(assistant_reply))
        
        # 计算基础分
        base_score = 8.0
        base_score -= len(issues) * 1.5
        
        # === 决定重写级别 ===
        rewrite_level = self._determine_rewrite_level(issues, conversation_mode)
        
        # === LLM 层评审（可选，规则已发现严重问题时跳过）===
        llm_score = None
        llm_issues = []
        improved = assistant_reply
        
        if rewrite_level == "rewrite" or (not issues and len(assistant_reply) > 10):
            try:
                llm_score, llm_issues, improved, llm_level = await self._llm_judge(
                    user_message, assistant_reply, conversation_mode
                )
                if llm_level == "rewrite" or rewrite_level == "rewrite":
                    rewrite_level = "rewrite"
                elif llm_level == "tone_fix" and rewrite_level == "none":
                    rewrite_level = "tone_fix"
            except Exception:
                pass
        
        # 综合评分
        if llm_score is not None:
            final_score = (base_score + llm_score) / 2
        else:
            final_score = base_score
        
        final_score = max(0, min(10, final_score))
        all_issues = issues + llm_issues
        
        # 如果规则发现了问题但 LLM 没有重写，用规则层建议重写
        if rewrite_level != "none" and improved == assistant_reply:
            improved = await self._rule_based_rewrite(
                assistant_reply, all_issues, conversation_mode, rewrite_level
            )
        
        # 生成建议
        suggestions = self._generate_suggestions(all_issues)
        
        # 判断是否合格
        is_good = final_score >= 7.0 and len(all_issues) <= 2 and rewrite_level == "none"
        
        # 记录打回历史（不合格时）
        if not is_good:
            self._rejection_history.append({
                "user_message": user_message[:100],
                "mode": conversation_mode,
                "score": final_score,
                "issues": all_issues,
                "rewrite_level": rewrite_level,
            })
            # 只保留最近 20 条
            if len(self._rejection_history) > 20:
                self._rejection_history = self._rejection_history[-20:]
        
        return JudgeResult(
            is_good=is_good,
            score=final_score,
            issues=all_issues,
            suggestions=suggestions,
            improved_reply=improved if not is_good else assistant_reply,
            rewrite_level=rewrite_level,
            rewrite_reason="; ".join(all_issues[:3]) if all_issues else "",
        )
    
    def _determine_rewrite_level(self, issues: list[str], mode: str) -> str:
        """根据问题数量和类型决定重写级别。"""
        if not issues:
            return "none"
        
        # 严重问题：模板味、客服腔、角色破坏
        severe_issues = [i for i in issues if any(k in i for k in ["模板味", "客服腔", "角色破坏"])]
        if len(severe_issues) >= 2:
            return "rewrite"
        
        # 中等问题：说教、模式错误
        medium_issues = [i for i in issues if any(k in i for k in ["说教", "模式错误"])]
        if len(medium_issues) >= 2 or len(issues) >= 4:
            return "rewrite"
        
        # 轻问题：追问、括号
        if issues:
            return "tone_fix"
        
        return "none"
    
    async def _rule_based_rewrite(
        self,
        reply: str,
        issues: list[str],
        mode: str,
        level: str,
    ) -> str:
        """基于规则的轻量级重写。"""
        improved = reply
        
        if level == "tone_fix":
            # 轻改：替换关键词、删括号、减追问
            for issue in issues:
                if "追问过多" in issue:
                    # 只保留第一个问号
                    improved = self._reduce_questions(improved)
                elif "括号" in issue:
                    import re
                    improved = re.sub(r'[（(].*?[)）]', '', improved)
                elif "模板味" in issue:
                    improved = improved.replace("以下是", "").replace("综上所述", "")
                elif "说教味" in issue:
                    improved = improved.replace("你应该", "要不试试").replace("你需要", "可以")
                elif "客服腔" in issue:
                    improved = improved.replace("为您服务", "").replace("祝您", "希望")
        
        elif level == "rewrite":
            # 重改：使用 LLM 重写
            try:
                improved = await self._llm_rewrite(reply, issues, mode)
            except Exception:
                # 如果 LLM 重写失败，用更强的规则重写
                improved = self._heavy_rule_rewrite(reply, issues)
        
        return improved.strip()
    
    def _reduce_questions(self, text: str) -> str:
        """减少追问数量，只保留第一个。"""
        parts = []
        question_seen = False
        for ch in text:
            if ch in "?？":
                if question_seen:
                    continue
                question_seen = True
            parts.append(ch)
        return "".join(parts)
    
    def _heavy_rule_rewrite(self, reply: str, issues: list[str]) -> str:
        """强规则重写（当 LLM 不可用时）。"""
        # 先执行所有 tone_fix
        improved = reply
        for issue in issues:
            if "模板味" in issue:
                for pattern in self.TEMPLATE_PATTERNS:
                    improved = improved.replace(pattern, "")
            elif "说教味" in issue:
                for pattern in self.PREACHY_PATTERNS:
                    improved = improved.replace(pattern, "")
            elif "客服腔" in issue:
                for pattern in self.SERVICE_PATTERNS:
                    improved = improved.replace(pattern, "")
        
        # 清理多余空白
        import re
        improved = re.sub(r'\n{3,}', '\n\n', improved)
        improved = re.sub(r'\s{2,}', ' ', improved)
        
        return improved.strip()
    
    async def _llm_rewrite(
        self,
        reply: str,
        issues: list[str],
        mode: str,
    ) -> str:
        """使用 LLM 进行整句重写。"""
        issues_text = "\n".join(f"- {issue}" for issue in issues)
        
        messages = [
            {"role": "system", "content": "你是一个回复改写专家。根据问题列表重写回复，保持原意但修复所有问题。只输出改写后的回复，不要解释。"},
            {"role": "user", "content": f"""请重写以下回复，修复这些问题：

【问题列表】
{issues_text}

【当前模式】{mode}

【原回复】
{reply}

【要求】
- 保持原意和情感
- 像朋友一样自然说话
- 不要模板腔、不要客服腔
- 单轮最多一个问题
- 不要括号动作描述
- 不自称AI

请直接输出改写后的回复："""},
        ]
        
        return await self._runtime.call("review", messages)
    
    def _check_template_smell(self, reply: str) -> list[str]:
        issues = []
        for pattern in self.TEMPLATE_PATTERNS:
            if pattern in reply:
                issues.append(f"模板味：包含'{pattern}'")
        return issues
    
    def _check_preachy(self, reply: str) -> list[str]:
        issues = []
        for pattern in self.PREACHY_PATTERNS:
            if pattern in reply:
                issues.append(f"说教味：包含'{pattern}'")
        return issues
    
    def _check_service_tone(self, reply: str) -> list[str]:
        issues = []
        for pattern in self.SERVICE_PATTERNS:
            if pattern in reply:
                issues.append(f"客服腔：包含'{pattern}'")
        return issues
    
    def _check_wrong_mode(self, reply: str, mode: str) -> list[str]:
        issues = []
        if mode == "chat":
            if reply.count("\n") > 5 and ("1." in reply or "- " in reply):
                issues.append("模式错误：chat mode 出现步骤化/列表化输出")
            if "根据" in reply and "建议" in reply:
                issues.append("模式错误：chat mode 过于正式建议")
        elif mode == "task":
            if len(reply) < 20 and "?" not in reply:
                issues.append("模式错误：task mode 回复过短")
        return issues
    
    def _check_bad_questions(self, reply: str) -> list[str]:
        issues = []
        question_count = reply.count("?") + reply.count("？")
        if question_count >= 2:
            issues.append(f"追问过多：单轮{question_count}个问题")
        sensitive_patterns = ["你为什么", "你父母", "你家庭", "你收入", "你体重"]
        for pattern in sensitive_patterns:
            if pattern in reply:
                issues.append(f"敏感问题：包含'{pattern}'")
        return issues
    
    def _check_parentheses(self, reply: str) -> list[str]:
        import re
        issues = []
        if re.search(r'[（(].*?[)）]', reply):
            issues.append("格式问题：包含括号动作/表情描述")
        return issues
    
    def _check_self_reference(self, reply: str) -> list[str]:
        issues = []
        bad_refs = ["我是AI", "作为AI", "我是人工智能", "我是助手", "我是智能体"]
        for ref in bad_refs:
            if ref in reply:
                issues.append(f"角色破坏：包含'{ref}'")
        return issues
    
    async def _llm_judge(
        self,
        user_message: str,
        reply: str,
        mode: str,
    ) -> tuple[float, list[str], str, str]:
        """使用 LLM 评审。"""
        
        messages = [
            {"role": "system", "content": "你是一个严格的对话质量评审员，只输出 JSON。"},
            {"role": "user", "content": f"""请评审以下AI回复的质量。

【用户消息】
{user_message}

【AI回复】
{reply}

【当前模式】
{mode}

请从以下维度评分（0-10）：
1. 自然度：像不像真人聊天
2. 角色一致性：是否保持朋友身份
3. 情绪承接：是否接住了用户的情绪或话头
4. 简洁度：有没有说太多
5. 人味：有没有模板味、客服腔

请输出 JSON：
{{
  "overall_score": 0-10,
  "issues": ["问题1"],
  "rewrite_level": "none|tone_fix|rewrite",
  "improved_version": "改进后的回复"
}}"""},
        ]
        
        text = await self._runtime.call("review", messages)
        
        json_start = text.find("{")
        json_end = text.rfind("}")
        if json_start >= 0 and json_end > json_start:
            try:
                data = json.loads(text[json_start:json_end + 1])
            except json.JSONDecodeError:
                data = {}
        else:
            data = {}
        
        score = float(data.get("overall_score", 7.0))
        issues = data.get("issues", [])
        improved = data.get("improved_version", reply)
        level = data.get("rewrite_level", "none")
        
        return score, issues, improved, level
    
    def _generate_suggestions(self, issues: list[str]) -> list[str]:
        suggestions = []
        for issue in issues:
            if "模板味" in issue:
                suggestions.append("删掉'以下是'、'首先'等模板词，直接说内容")
            elif "说教味" in issue:
                suggestions.append("把'你应该'改成'我觉得可以试试'或'要不...'")
            elif "客服腔" in issue:
                suggestions.append("删掉'为您服务'、'祝您'等，像朋友一样说话")
            elif "模式错误" in issue:
                suggestions.append("检查当前模式，chat mode要轻，task mode要实")
            elif "追问过多" in issue:
                suggestions.append("单轮最多一个问题，或者不问直接说")
            elif "括号" in issue:
                suggestions.append("删掉括号里的动作描述")
            elif "角色破坏" in issue:
                suggestions.append("不要提自己是AI，用'我'就好")
        return suggestions
    
    def get_rejection_patterns(self) -> dict[str, Any]:
        """获取打回模式统计，用于 prompt 调优闭环。"""
        from collections import Counter
        
        if not self._rejection_history:
            return {"total": 0, "patterns": {}}
        
        all_issues = []
        for record in self._rejection_history:
            all_issues.extend(record["issues"])
        
        # 提取问题类型（去掉具体文本，保留类别）
        issue_types = []
        for issue in all_issues:
            if "模板味" in issue:
                issue_types.append("template")
            elif "说教味" in issue:
                issue_types.append("preachy")
            elif "客服腔" in issue:
                issue_types.append("service_tone")
            elif "模式错误" in issue:
                issue_types.append("wrong_mode")
            elif "追问过多" in issue:
                issue_types.append("too_many_questions")
            elif "括号" in issue:
                issue_types.append("parentheses")
            elif "角色破坏" in issue:
                issue_types.append("self_reference")
            elif "敏感问题" in issue:
                issue_types.append("sensitive")
            else:
                issue_types.append("other")
        
        counts = Counter(issue_types)
        
        return {
            "total": len(self._rejection_history),
            "patterns": dict(counts.most_common()),
            "recent_issues": self._rejection_history[-5:],
        }
    
    async def judge(
        self,
        user_message: str,
        assistant_reply: str,
        conversation_mode: str = "chat",
        conversation_state: dict[str, Any] | None = None,
    ) -> JudgeResult:
        """评审回复质量。"""
        
        issues = []
        
        # === 规则层检测 ===
        issues.extend(self._check_template_smell(assistant_reply))
        issues.extend(self._check_preachy(assistant_reply))
        issues.extend(self._check_service_tone(assistant_reply))
        issues.extend(self._check_wrong_mode(assistant_reply, conversation_mode))
        issues.extend(self._check_bad_questions(assistant_reply))
        issues.extend(self._check_parentheses(assistant_reply))
        issues.extend(self._check_self_reference(assistant_reply))
        
        # 计算基础分
        base_score = 8.0
        base_score -= len(issues) * 1.5
        
        # === LLM 层评审（可选） ===
        llm_score = None
        llm_issues = []
        if self._runtime and len(assistant_reply) > 10:
            try:
                llm_score, llm_issues, improved = await self._llm_judge(
                    user_message, assistant_reply, conversation_mode
                )
            except Exception:
                improved = assistant_reply
        else:
            improved = assistant_reply
        
        # 综合评分
        if llm_score is not None:
            final_score = (base_score + llm_score) / 2
        else:
            final_score = base_score
        
        final_score = max(0, min(10, final_score))
        
        all_issues = issues + llm_issues
        
        # 生成建议
        suggestions = self._generate_suggestions(all_issues)
        
        is_good = final_score >= 7.0 and len(all_issues) <= 2
        
        # 确定重写级别和原因
        rewrite_level = "none" if is_good else "tone_fix"
        rewrite_reason = ""
        if all_issues:
            rewrite_reason = all_issues[0]
        
        return JudgeResult(
            is_good=is_good,
            score=final_score,
            issues=all_issues,
            suggestions=suggestions,
            improved_reply=improved if not is_good else assistant_reply,
            rewrite_level=rewrite_level,
            rewrite_reason=rewrite_reason,
        )
    
    def _check_template_smell(self, reply: str) -> list[str]:
        """检测模板味。"""
        issues = []
        for pattern in self.TEMPLATE_PATTERNS:
            if pattern in reply:
                issues.append(f"模板味：包含'{pattern}'")
        return issues
    
    def _check_preachy(self, reply: str) -> list[str]:
        """检测说教味。"""
        issues = []
        for pattern in self.PREACHY_PATTERNS:
            if pattern in reply:
                issues.append(f"说教味：包含'{pattern}'")
        return issues
    
    def _check_service_tone(self, reply: str) -> list[str]:
        """检测客服腔。"""
        issues = []
        for pattern in self.SERVICE_PATTERNS:
            if pattern in reply:
                issues.append(f"客服腔：包含'{pattern}'")
        return issues
    
    def _check_wrong_mode(self, reply: str, mode: str) -> list[str]:
        """检测模式错误。"""
        issues = []
        
        if mode == "chat":
            # chat mode 不应该有步骤化输出
            if reply.count("\n") > 5 and ("1." in reply or "- " in reply):
                issues.append("模式错误：chat mode 出现步骤化/列表化输出")
            
            # chat mode 不应该太正式
            if "根据" in reply and "建议" in reply:
                issues.append("模式错误：chat mode 过于正式建议")
        
        elif mode == "task":
            # task mode 应该给具体方案
            if len(reply) < 20 and "?" not in reply:
                issues.append("模式错误：task mode 回复过短")
        
        return issues
    
    def _check_bad_questions(self, reply: str) -> list[str]:
        """检测不该问的问题。"""
        issues = []
        
        # 情绪场景中不该连环追问
        question_count = reply.count("?") + reply.count("？")
        if question_count >= 2:
            issues.append(f"追问过多：单轮{question_count}个问题")
        
        # 敏感问题
        sensitive_patterns = [
            "你为什么",
            "你父母",
            "你家庭",
            "你收入",
            "你体重",
        ]
        for pattern in sensitive_patterns:
            if pattern in reply:
                issues.append(f"敏感问题：包含'{pattern}'")
        
        return issues
    
    def _check_parentheses(self, reply: str) -> list[str]:
        """检测括号动作描述。"""
        import re
        issues = []
        
        # 检测（...）或(...)
        if re.search(r'[（(].*?[)）]', reply):
            issues.append("格式问题：包含括号动作/表情描述")
        
        return issues
    
    def _check_self_reference(self, reply: str) -> list[str]:
        """检测自我指代问题。"""
        issues = []
        
        bad_refs = ["我是AI", "作为AI", "我是人工智能", "我是助手", "我是智能体"]
        for ref in bad_refs:
            if ref in reply:
                issues.append(f"角色破坏：包含'{ref}'")
        
        return issues
    
    async def _llm_judge(
        self,
        user_message: str,
        reply: str,
        mode: str,
    ) -> tuple[float, list[str], str]:
        """使用 LLM 评审。"""
        
        prompt = f"""请评审以下AI回复的质量。

【用户消息】
{user_message}

【AI回复】
{reply}

【当前模式】
{mode}

请从以下维度评分（0-10）：
1. 自然度：像不像真人聊天
2. 角色一致性：是否保持朋友身份（不是客服/助手/老师）
3. 情绪承接：是否接住了用户的情绪或话头
4. 简洁度：有没有说太多
5. 人味：有没有模板味、客服腔、说明书味

请输出 JSON：
{{
  "overall_score": 0-10,
  "issues": ["问题1", "问题2"],
  "improved_version": "改进后的回复"
}}"""

        text = await self._runtime.call(
            "review",
            messages=[
                {"role": "system", "content": "你是一个严格的对话质量评审员，只输出 JSON。"},
                {"role": "user", "content": prompt},
            ],
        )
        
        # 提取 JSON
        json_start = text.find("{")
        json_end = text.rfind("}")
        if json_start >= 0 and json_end > json_start:
            try:
                data = json.loads(text[json_start:json_end + 1])
            except json.JSONDecodeError:
                data = {}
        else:
            data = {}
        
        score = float(data.get("overall_score", 7.0))
        issues = data.get("issues", [])
        improved = data.get("improved_version", reply)
        
        return score, issues, improved
    
    def _generate_suggestions(self, issues: list[str]) -> list[str]:
        """根据问题生成建议。"""
        suggestions = []
        
        for issue in issues:
            if "模板味" in issue:
                suggestions.append("删掉'以下是'、'首先'等模板词，直接说内容")
            elif "说教味" in issue:
                suggestions.append("把'你应该'改成'我觉得可以试试'或'要不...'")
            elif "客服腔" in issue:
                suggestions.append("删掉'为您服务'、'祝您'等，像朋友一样说话")
            elif "模式错误" in issue:
                suggestions.append("检查当前模式，chat mode要轻，task mode要实")
            elif "追问过多" in issue:
                suggestions.append("单轮最多一个问题，或者不问直接说")
            elif "括号" in issue:
                suggestions.append("删掉括号里的动作描述")
            elif "角色破坏" in issue:
                suggestions.append("不要提自己是AI，用'我'就好")
        
        return suggestions
