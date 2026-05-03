# LEGACY: response_reviewer.py is deprecated. Use companion_agent/v2/ instead.
"""Response Reviewer - 回复后评审

每轮生成回复后，做一次轻量评估：
1. 有没有模板味？
2. 有没有说教感？
3. 有没有误触发任务模式？
4. 有没有问了不该问的问题？

不是过滤，是评分+提示。分数太低时可以给修正建议。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from prototype_demo.llm_client import get_llm_client


@dataclass
class ReviewResult:
    """评审结果"""
    overall_score: float  # 0-10
    is_good_enough: bool  # 是否可以直接使用
    
    # 各维度评分
    template_score: float  # 模板味（10=完全没模板味）
    preach_score: float    # 说教感（10=完全不说教）
    mode_match_score: float  # 模式匹配（10=完美匹配）
    persona_score: float   # 人格一致性（10=完全符合角色）
    
    # 问题列表
    issues: list[str] = field(default_factory=list)
    
    # 修正建议
    suggestion: str = ""
    
    # 是否触发重写
    needs_rewrite: bool = False


# 模板味关键词（作为 LLM 参考，不是硬规则）
_TEMPLATE_PATTERNS = [
    "以下是", "首先", "其次", "最后", "总结", "综上所述",
    "建议如下", "以下是一些建议", "希望对你有帮助",
    "作为你的", "我理解你的", "你的感受是正常的",
    "保持积极", "不要灰心", "相信自己", "加油",
]

# 说教味指标
_PREACH_PATTERNS = [
    "你应该", "你必须", "你需要", "你要",
    "重要的是", "关键是", "记住",
    "这样才能", "否则你会", "如果不",
]


async def review_response(
    user_message: str,
    assistant_response: str,
    intended_mode: str = "chat",  # chat/task/mixed
    intended_tone: str = "natural",
) -> ReviewResult:
    """评审生成的回复"""
    
    # 快速路径：明显问题直接扣分
    quick_score = 10.0
    issues = []
    
    # 检查模板味
    template_hits = sum(1 for p in _TEMPLATE_PATTERNS if p in assistant_response)
    if template_hits >= 2:
        quick_score -= 3
        issues.append(f"模板味明显（命中{template_hits}个模板词）")
    elif template_hits == 1:
        quick_score -= 1
    
    # 检查说教
    preach_hits = sum(1 for p in _PREACH_PATTERNS if p in assistant_response)
    if preach_hits >= 2:
        quick_score -= 2
        issues.append(f"说教感强（命中{preach_hits}个说教词）")
    elif preach_hits == 1:
        quick_score -= 0.5
    
    # 检查模式错配
    if intended_mode == "chat" and len(assistant_response) > 200:
        quick_score -= 2
        issues.append("chat mode 回复过长，可能误触任务模式")
    
    # 检查过度提问
    question_count = assistant_response.count("？") + assistant_response.count("?")
    if question_count >= 3:
        quick_score -= 1.5
        issues.append("连续追问过多")
    
    # 如果快速检查分数够高，直接返回
    if quick_score >= 8 and not issues:
        return ReviewResult(
            overall_score=quick_score,
            is_good_enough=True,
            template_score=10 - template_hits * 2,
            preach_score=10 - preach_hits * 2,
            mode_match_score=10,
            persona_score=9,
            issues=[],
            suggestion="",
            needs_rewrite=False,
        )
    
    # LLM 深度评审
    llm = get_llm_client()
    
    prompt = f"""你是一个对话质量评估专家。请评审这个 AI 回复。

【原始用户消息】
{user_message}

【AI 回复】
{assistant_response}

【预期模式】
{intended_mode}（chat=闲聊陪伴, task=任务执行, mixed=混合）
【预期语调】
{intended_tone}

【评审标准】
1. 模板味（0-10）：有没有"客服腔""说明书味"？像不像真人说话？
2. 说教感（0-10）：有没有"你应该""你必须"？有没有爹味？
3. 模式匹配（0-10）：chat mode 就应该短+接话，task mode 可以长+给方案。匹配吗？
4. 人格一致（0-10）：像不像"很熟的室友"？有没有突然变正经？

【特别关注】
- 回复长度：chat mode 超过150字要扣分
- 提问数量：一轮最多1个问题，超过要扣分
- 行动 > 安慰：说"我给你点奶茶"比"别难过"好
- 具体 > 抽象：说"食堂二楼"比"吃点好的"好

请 JSON 输出：
{{
    "overall_score": 0-10,
    "template_score": 0-10,
    "preach_score": 0-10,
    "mode_match_score": 0-10,
    "persona_score": 0-10,
    "issues": ["问题1", "问题2"],
    "suggestion": "如果分数<7，给出具体修改建议",
    "needs_rewrite": true|false
}}"""
    
    try:
        response = await llm.complete(prompt, max_tokens=300, temperature=0.3)
        cleaned = response.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            if len(lines) > 2:
                cleaned = "\n".join(lines[1:-1])
            else:
                cleaned = cleaned.replace("```", "").replace("json", "")
        cleaned = cleaned.strip()
        
        result = json.loads(cleaned)
        
        overall = float(result.get("overall_score", quick_score))
        
        # 合并快速检查发现的问题
        all_issues = issues + result.get("issues", [])
        
        return ReviewResult(
            overall_score=overall,
            is_good_enough=overall >= 7 and len(all_issues) <= 1,
            template_score=float(result.get("template_score", 10)),
            preach_score=float(result.get("preach_score", 10)),
            mode_match_score=float(result.get("mode_match_score", 10)),
            persona_score=float(result.get("persona_score", 10)),
            issues=all_issues,
            suggestion=result.get("suggestion", ""),
            needs_rewrite=result.get("needs_rewrite", overall < 6),
        )
    
    except Exception:
        # LLM 失败，用快速检查结果
        return ReviewResult(
            overall_score=quick_score,
            is_good_enough=quick_score >= 7,
            template_score=10 - template_hits * 2,
            preach_score=10 - preach_hits * 2,
            mode_match_score=8 if issues else 10,
            persona_score=8,
            issues=issues,
            suggestion="" if quick_score >= 7 else "建议简化回复，减少模板用语",
            needs_rewrite=quick_score < 6,
        )


async def rewrite_response(
    user_message: str,
    original_response: str,
    review_result: ReviewResult,
    persona_examples: str = "",
) -> str:
    """基于评审结果重写回复"""
    
    if not review_result.needs_rewrite:
        return original_response
    
    llm = get_llm_client()
    
    issues_str = "\n".join([f"- {i}" for i in review_result.issues])
    
    prompt = f"""请重写这个 AI 回复，解决以下问题。

【用户消息】
{user_message}

【原回复（有问题）】
{original_response}

【问题列表】
{issues_str}

【修改要求】
1. 像真人说话，不要像客服
2. 不要说教，不要说"你应该"
3. 简短，chat mode 回复控制在100字内
4. 给一个具体行动或细节，不要泛泛安慰
5. 允许口语化、留白、不完整的句子

【角色参考】
{persona_examples[:500]}

请直接输出修改后的回复，不要解释修改了什么："""
    
    try:
        response = await llm.complete(prompt, max_tokens=200, temperature=0.7)
        return response.strip()
    except Exception:
        # 如果重写失败，返回原文但截断
        if len(original_response) > 100:
            return original_response[:100] + "..."
        return original_response
