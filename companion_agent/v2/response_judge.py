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
    
    # 本科生陪伴场景下的坏味道模式（优先规则检测）
    BAD_PATTERNS = {
        "psych_therapy_tone": [
            "我理解你的感受", "这很重要", "你的感受很重要", "请相信",
            "接纳自己", "自我关怀", "情绪价值", "内在力量",
        ],
        "customer_service_tone": [
            "很高兴", "为您服务", "请问还有什么", "感谢您的", "祝您",
            "欢迎", "请随时", "如有问题",
        ],
        "teacher_preaching_tone": [
            "你应该", "你需要", "你必须", "重要的是", "记住要",
            "不要忘记", "关键在于", "本质上", "其实你应该", "建议你制定",
            "保持积极心态", "合理规划", "养成良好的",
        ],
        "over_summary_tone": [
            "综上所述", "总结一下", "总而言之", "归纳一下",
            "首先", "其次", "最后", "第一", "第二", "第三",
        ],
        "over_question_tone": [
            "为什么呢", "你觉得呢", "可以吗", "好吗", "对吗",
        ],
        "abrupt_thread_pull": [
            "不过你之前", "但是你还有", "虽然你在", "我们回到",
            "别忘了你", "你之前说", "先别管这个",
        ],
        "identity_defensive_tone": [
            "作为AI", "我是人工智能", "我是助手", "我是智能体",
            "我只是一款", "我的程序", "我的算法", "我的训练数据",
        ],
        "list_when_chatting": [
            "1.", "2.", "3.", "4.", "5.",
        ],
        "too_many_modal_questions": [
            "能不能", "可不可以", "行吗", "好吗", "对吗",
        ],
    }
    
    BAD_PATTERN_SCORES = {
        "psych_therapy_tone": 2.0,
        "customer_service_tone": 2.0,
        "teacher_preaching_tone": 1.5,
        "over_summary_tone": 1.0,
        "over_question_tone": 0.5,
        "abrupt_thread_pull": 2.0,
        "identity_defensive_tone": 2.0,
        "list_when_chatting": 1.0,
        "too_many_modal_questions": 0.5,
        "cold_boundary_ack": 1.5,
    }
    
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
        """评审回复质量。规则优先，只有命中坏味道时才触发 LLM rewrite。"""
        
        issues = []
        
        # === 规则层检测（本科生陪伴场景坏味道）===
        issues.extend(self._check_bad_patterns(assistant_reply))
        issues.extend(self._check_wrong_mode(assistant_reply, conversation_mode))
        issues.extend(self._check_bad_questions(assistant_reply, conversation_mode))
        issues.extend(self._check_parentheses(assistant_reply))
        issues.extend(self._check_self_reference(assistant_reply))
        issues.extend(self._check_boundary_ack(user_message, assistant_reply))
        
        # 计算基础分
        base_score = 8.0
        for issue in issues:
            for category, score in self.BAD_PATTERN_SCORES.items():
                if category in issue:
                    base_score -= score
                    break
            else:
                base_score -= 1.0
        
        # === 决定是否需要 LLM rewrite ===
        # 只有规则发现问题且比较严重时才用 LLM
        should_run_llm = False
        rewrite_level = "none"
        
        severe_issues = [i for i in issues if any(
            k in i for k in ["psych_therapy_tone", "customer_service_tone", "abrupt_thread_pull"]
        )]
        medium_issues = [i for i in issues if any(
            k in i for k in ["teacher_preaching_tone", "over_summary_tone"]
        )]
        
        if len(severe_issues) >= 1:
            rewrite_level = "rewrite"
            should_run_llm = True
        elif len(medium_issues) >= 2 or len(issues) >= 4:
            rewrite_level = "rewrite"
            should_run_llm = True
        elif len(issues) >= 1:
            rewrite_level = "tone_fix"
            # tone_fix 用规则重写，不调用 LLM
            should_run_llm = False
        
        # === LLM 层评审（仅严重问题时）===
        llm_score = None
        llm_issues = []
        improved = assistant_reply
        
        if should_run_llm and self._runtime:
            try:
                llm_score, llm_issues, improved, llm_level = await self._llm_judge(
                    user_message, assistant_reply, conversation_mode
                )
                if llm_level == "rewrite":
                    rewrite_level = "rewrite"
            except Exception:
                # LLM 失败时回退到规则重写
                improved = self._rule_based_rewrite(
                    assistant_reply, issues, conversation_mode, rewrite_level
                )
        elif rewrite_level == "tone_fix":
            # 轻问题直接用规则重写
            improved = self._rule_based_rewrite(
                assistant_reply, issues, conversation_mode, "tone_fix"
            )
        
        # 综合评分
        if llm_score is not None:
            final_score = (base_score + llm_score) / 2
        else:
            final_score = base_score
        
        final_score = max(0, min(10, final_score))
        all_issues = issues + llm_issues
        
        # 生成建议
        suggestions = self._generate_suggestions(all_issues)
        
        # 判断是否合格
        is_good = final_score >= 7.0 and len(all_issues) <= 2 and rewrite_level == "none"
        
        # 记录打回历史
        if not is_good:
            self._rejection_history.append({
                "user_message": user_message[:100],
                "mode": conversation_mode,
                "score": final_score,
                "issues": all_issues,
                "rewrite_level": rewrite_level,
            })
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
    
    def _check_bad_patterns(self, reply: str) -> list[str]:
        """检测本科生陪伴场景下的坏味道。"""
        issues = []
        for category, patterns in self.BAD_PATTERNS.items():
            for pattern in patterns:
                if pattern in reply:
                    issues.append(f"{category}：包含'{pattern}'")
                    break  # 每个类别只报一次
        return issues
    
    def _check_template_smell(self, reply: str) -> list[str]:
        """兼容旧接口，合并到 _check_bad_patterns。"""
        return self._check_bad_patterns(reply)
    
    def _check_preachy(self, reply: str) -> list[str]:
        """兼容旧接口。"""
        issues = []
        for pattern in self.BAD_PATTERNS.get("teacher_preaching_tone", []):
            if pattern in reply:
                issues.append(f"teacher_preaching_tone：包含'{pattern}'")
                break
        return issues
    
    def _check_service_tone(self, reply: str) -> list[str]:
        """兼容旧接口。"""
        issues = []
        for pattern in self.BAD_PATTERNS.get("customer_service_tone", []):
            if pattern in reply:
                issues.append(f"customer_service_tone：包含'{pattern}'")
                break
        return issues
    
    def _check_wrong_mode(self, reply: str, mode: str) -> list[str]:
        issues = []
        if mode in ("chat", "quiet", "stabilize"):
            if reply.count("\n") > 2 and ("1." in reply or "- " in reply or "* " in reply):
                issues.append("模式错误：chat mode 出现步骤化/列表化输出")
            if "根据" in reply and "建议" in reply:
                issues.append("模式错误：chat mode 过于正式建议")
            # Detect list_when_chatting from BAD_PATTERNS
            for pattern in self.BAD_PATTERNS.get("list_when_chatting", []):
                if pattern in reply:
                    issues.append("list_when_chatting：chat mode 出现编号列表")
                    break
        elif mode == "task":
            if len(reply) < 20 and "?" not in reply:
                issues.append("模式错误：task mode 回复过短")
        return issues
    
    def _check_bad_questions(self, reply: str, mode: str = "") -> list[str]:
        issues = []
        question_count = reply.count("?") + reply.count("？")
        if question_count >= 2:
            issues.append(f"追问过多：单轮{question_count}个问题")
        # Quiet mode should have zero questions
        if mode == "quiet" and question_count >= 1:
            issues.append("over_question_tone：quiet 回复不应带问号")
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
    
    def _check_boundary_ack(self, user_message: str, reply: str) -> list[str]:
        """Check if boundary acknowledgment is too cold/short.
        
        When user says 'don't remember this' or 'don't analyze me',
        the reply should give warm confirmation, not just '懂的'.
        """
        issues = []
        boundary_markers = ["别记", "别分析", "不想被你分析", "别解读", "别贴标签"]
        if any(marker in user_message for marker in boundary_markers):
            # If reply is very short or just generic acknowledgment
            if len(reply) < 12 or reply.strip() in ("懂的", "懂", "好的", "知道了"):
                issues.append("cold_boundary_ack: 用户要求不记/不分析时回复过短或太冷")
            # If reply only says '懂的' without any warm confirmation
            elif reply.strip().startswith("懂的") and len(reply) < 20:
                issues.append("cold_boundary_ack: 用户要求不记/不分析时只用'懂的'开头")
        return issues
    
    def _rule_based_rewrite(
        self,
        reply: str,
        issues: list[str],
        mode: str,
        level: str,
    ) -> str:
        """基于规则的重写，不调用 LLM。
        
        level:
        - "tone_fix": 只改语气词
        - "rewrite": 尝试调整句式
        """
        improved = reply
        
        # 替换坏味道词组
        replacements = {
            "psych_therapy_tone": {
                "我理解你的感受": "我懂",
                "这很重要": "",
                "你的感受很重要": "",
                "请相信": "",
                "接纳自己": "先别急着否定自己",
                "自我关怀": "对自己好一点",
                "情绪价值": "",
                "内在力量": "",
            },
            "customer_service_tone": {
                "很高兴": "",
                "为您服务": "",
                "请问还有什么": "",
                "感谢您的": "",
                "祝您": "",
                "欢迎": "",
                "请随时": "",
                "如有问题": "",
            },
            "cold_boundary_ack": {
                "懂的": "放心，不记这个",
                "懂": "懂，正常聊",
            },
            "teacher_preaching_tone": {
                "你应该": "你可以试试",
                "你需要": "要不",
                "你必须": "",
                "重要的是": "",
                "记住要": "",
                "不要忘记": "",
                "关键在于": "",
                "本质上": "",
                "其实你应该": "",
                "建议你制定": "",
                "保持积极心态": "",
                "合理规划": "",
                "养成良好的": "",
            },
            "over_summary_tone": {
                "综上所述": "",
                "总结一下": "",
                "总而言之": "",
                "归纳一下": "",
                "首先": "",
                "其次": "",
                "最后": "",
                "第一": "",
                "第二": "",
                "第三": "",
            },
            "abrupt_thread_pull": {
                "不过你之前": "",
                "但是你还有": "",
                "虽然你在": "",
                "我们回到": "",
                "别忘了你": "",
                "你之前说": "",
                "先别管这个": "",
            },
            "identity_defensive_tone": {
                "作为AI": "",
                "我是人工智能": "",
                "我是助手": "",
                "我是智能体": "",
                "我只是一款": "",
                "我的程序": "",
                "我的算法": "",
                "我的训练数据": "",
            },
            "list_when_chatting": {
                "1.": "",
                "2.": "",
                "3.": "",
                "4.": "",
                "5.": "",
            },
        }
        
        for issue in issues:
            for category, mapping in replacements.items():
                if category in issue:
                    for bad, good in mapping.items():
                        if bad in improved:
                            if good:
                                improved = improved.replace(bad, good)
                            else:
                                improved = improved.replace(bad, "")
        
        # 清理多余空格和标点
        improved = improved.replace("  ", " ").strip()
        improved = improved.replace("。。", "。")
        improved = improved.replace("，，", "，")
        
        # 如果 rewrite 级别较高，尝试更激进的调整
        if level == "rewrite":
            # 移除列表化输出（chat mode）
            if mode == "chat":
                lines = improved.split("\n")
                cleaned_lines = []
                for line in lines:
                    stripped = line.strip()
                    if stripped.startswith(("1.", "2.", "3.", "- ", "* ", "• ")):
                        cleaned_lines.append(stripped[2:].strip())
                    else:
                        cleaned_lines.append(line)
                improved = "\n".join(cleaned_lines)
            
            # 移除空行过多的情况
            improved = "\n".join(line for line in improved.split("\n") if line.strip())
        
        return improved.strip() if improved.strip() else reply
    
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
