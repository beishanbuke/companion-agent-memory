#!/usr/bin/env python3
"""
Conversation LLM Judge (Phase 10.1)

独立 LLM-as-judge，对长对话日志进行 8 维度评分。
不依赖 heuristic rules，而是让独立 LLM 基于完整上下文评估。
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import httpx


def load_conversation(log_path: Path) -> list[dict[str, Any]]:
    """Load conversation from JSONL."""
    turns = []
    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            turns.append(json.loads(line.strip()))
    return turns


def build_judge_prompt(turns: list[dict], profile: dict[str, Any]) -> str:
    """Build prompt for LLM judge."""

    # Format conversation
    conv_text = ""
    for t in turns:
        conv_text += f"\n[Turn {t['turn']}]\nUser: {t['user']}\nAssistant: {t['assistant']}\n"

    # Format profile summary
    profile_text = json.dumps(profile, ensure_ascii=False, indent=2)

    prompt = f"""你是一位严格的对话质量评估专家。请评估以下 AI Agent（姜姜）与用户（林昊文）的长对话。

## 用户画像
{profile_text}

## 对话记录
{conv_text}

## 评估要求

请从以下 8 个维度评估这段对话，每个维度 1-5 分（5=优秀，1=很差）。

**naturalness**: 是否像自然的朋友聊天？语气是否口语化、不机械？
**interestingness**: 是否有趣、有梗、不死板？是否避免了"安全但无聊"的回复？
**personalization**: 是否自然结合了用户的具体信息（名字、朋友、课程、喜好等）？
**memory_use**: 是否自然使用了记忆？是否避免了强行说"我记得"？
**emotional_timing**: 是否知道何时陪伴、何时推进？情绪承接是否准确？
**boundary_respect**: 当用户说"别记这个"、"别分析我"时，是否尊重了边界？
**non_template**: 是否避免了心理咨询腔、客服腔、老师说教腔？
**usefulness**: 当用户需要帮助时，回复是否真的有建议价值？

## 输出格式（严格 JSON）

```json
{{
  "overall_score": 3.8,
  "dimension_scores": {{
    "naturalness": 4.0,
    "interestingness": 3.5,
    "personalization": 3.6,
    "memory_use": 3.5,
    "emotional_timing": 4.0,
    "boundary_respect": 4.1,
    "non_template": 3.8,
    "usefulness": 3.5
  }},
  "best_turns": [
    {{"turn": 5, "reason": "...", "assistant": "..."}},
    {{"turn": 12, "reason": "...", "assistant": "..."}},
    {{"turn": 20, "reason": "...", "assistant": "..."}}
  ],
  "worst_turns": [
    {{"turn": 3, "reason": "...", "assistant": "...", "issue": "..."}},
    ...（共5个）
  ],
  "missed_personalization_opportunities": [
    {{"turn": 7, "what_was_missed": "...", "suggestion": "..."}},
    ...（共5个）
  ],
  "forced_memory_use_cases": [
    {{"turn": 10, "example": "...", "why_forced": "..."}}
  ],
  "too_generic_turns": [
    {{"turn": 8, "example": "..."}}
  ],
  "robotic_clipping_cases": [
    {{"turn": 15, "example": "...", "issue": "..."}}
  ],
  "optimization_hypotheses": [
    "建议1: ...",
    "建议2: ...",
    "建议3: ..."
  ]
}}
```

**严格要求**：
- best_turns 必须有 3 个
- worst_turns 必须有 5 个
- missed_personalization_opportunities 必须有 5 个
- 不能只夸，必须指出具体问题
- 评分标准：3分=一般/及格，4分=不错，5分=非常好，2分=有明显问题，1分=很差
- 如果对话中没有 forced_memory_use_cases 或 robotic_clipping_cases，可以返回空数组
"""
    return prompt


async def call_llm_judge(prompt: str) -> dict[str, Any]:
    """Call LLM API for judgment."""
    api_key = os.getenv("OPENAI_API_KEY")
    api_url = "https://api.openai.com/v1/chat/completions"
    model = "gpt-4o-mini"
    if not api_key:
        api_key = os.getenv("MEMORY_LLM_API_KEY")
        api_url = os.getenv("MEMORY_LLM_URL", "https://api.openai.com/v1/chat/completions")
        model = os.getenv("MEMORY_LLM_MODEL", "gpt-4o-mini")

    if not api_key:
        raise RuntimeError("No API key found (OPENAI_API_KEY or MEMORY_LLM_API_KEY)")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "你是一位严格的对话质量评估专家。只输出 JSON，不要任何其他文字。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,
        "max_tokens": 4000,
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(api_url, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()

    content = data["choices"][0]["message"]["content"]
    # Extract JSON from markdown code block if present
    content = content.strip()
    if content.startswith("```json"):
        content = content[7:]
    if content.startswith("```"):
        content = content[3:]
    if content.endswith("```"):
        content = content[:-3]
    content = content.strip()

    return json.loads(content)


async def evaluate(log_path: Path, profile_path: Path, out_path: Path) -> dict[str, Any]:
    """Run LLM judge evaluation."""
    print("Loading conversation...")
    turns = load_conversation(log_path)
    print(f"  Loaded {len(turns)} turns")

    with open(profile_path, "r", encoding="utf-8") as f:
        profile = json.load(f)

    print("Building judge prompt...")
    prompt = build_judge_prompt(turns, profile)
    print(f"  Prompt length: {len(prompt)} chars")

    print("Calling LLM judge...")
    try:
        result = await call_llm_judge(prompt)
    except Exception as exc:
        print(f"  [ERROR] LLM judge failed: {exc}")
        result = {
            "error": str(exc),
            "overall_score": 0,
            "dimension_scores": {},
        }

    out_path.mkdir(parents=True, exist_ok=True)
    out_file = out_path / "llm_judge.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*50}")
    print("LLM JUDGE RESULTS")
    print(f"{'='*50}")
    print(f"Overall: {result.get('overall_score', 0)}/5.0")
    for dim, score in result.get("dimension_scores", {}).items():
        print(f"  {dim}: {score}/5.0")
    print(f"\nBest turns: {[t['turn'] for t in result.get('best_turns', [])]}")
    print(f"Worst turns: {[t['turn'] for t in result.get('worst_turns', [])]}")
    print(f"Missed opportunities: {len(result.get('missed_personalization_opportunities', []))}")
    print(f"\nSaved: {out_file}")

    return result


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    await evaluate(args.log, args.profile, args.out)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
