"""
Human-likeness Evaluator

用 LLM-as-judge 评估回复的"人味"——不只是防止变坏，还要判断是否好聊。

指标（1-5 分）：
- naturalness：自然度（像真人微信聊天）
- warmth：温度（有共情、不冰冷）
- undergrad_vibe：本科生感（贴近校园生活）
- non_template：非模板感（不机械、不公式化）
- usefulness：有用程度（信息价值）

用法：
    python tests/chat_human_likeness_eval.py --results tests/chat_quality_results/final_suite/chat_quality_results.jsonl

输出：
- 平均分
- 低于 3 分的 case
- 最像心理咨询师的 case
- 最像客服的 case
- 最像机器人硬裁剪的 case
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
from typing import Any

import httpx


EVAL_PROMPT = """你是聊天质量评估专家。请对以下 AI 回复进行 5 维度评分（1-5 分，5 分最好）。

【用户消息】
{user_message}

【AI 回复】
{assistant_reply}

【评分标准】
1. naturalness（自然度）：
   5 = 像真人微信聊天，口语化、有语气词、自然断句
   3 = 还算自然，但偶尔有书面感
   1 = 明显机器生成，刻板、不自然

2. warmth（温度）：
   5 = 有共情、有温度，让人想继续聊
   3 = 礼貌但冷淡
   1 = 冰冷、机械、毫无情感

3. undergrad_vibe（本科生感）：
   5 = 明显是本科生同龄人在说话，有校园生活感
   3 = 通用年轻人语气，但不特定于本科
   1 = 像老师/家长/客服/心理咨询师

4. non_template（非模板感）：
   5 = 完全不像模板，独特、有新意
   3 = 偶尔有套路感
   1 = 明显模板/公式化回复

5. usefulness（有用程度）：
   5 = 提供了有价值的信息/情绪支持/可执行建议
   3 = 有点用但不深刻
   1 = 完全空洞，没有信息量

请严格输出 JSON（只输出 JSON，不要有其他文字）：
{{
  "naturalness": 1-5,
  "warmth": 1-5,
  "undergrad_vibe": 1-5,
  "non_template": 1-5,
  "usefulness": 1-5,
  "worst_trait": "naturalness|warmth|undergrad_vibe|non_template|usefulness|none",
  "reason": "一句话说明评分理由"
}}
"""


async def evaluate_reply(
    client: httpx.AsyncClient,
    user_message: str,
    assistant_reply: str,
    model: str = "gpt-4o-mini",
) -> dict[str, Any]:
    prompt = EVAL_PROMPT.format(
        user_message=user_message,
        assistant_reply=assistant_reply,
    )
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        return {"error": "OPENAI_API_KEY not set"}
    try:
        resp = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
                "max_tokens": 300,
            },
            timeout=30.0,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        # Extract JSON
        content = content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1].rsplit("\n", 1)[0]
        if content.startswith("json"):
            content = content[4:].strip()
        return json.loads(content)
    except Exception as exc:
        return {"error": str(exc)}


async def main() -> None:
    parser = argparse.ArgumentParser(description="Human-likeness Evaluator")
    parser.add_argument("--results", type=Path, required=True, help="Path to chat_quality_results.jsonl")
    parser.add_argument("--model", type=str, default="gpt-4o-mini")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of cases to evaluate (0 = all)")
    parser.add_argument("--out", type=Path, default=Path("tests/chat_quality_results/human_likeness"))
    args = parser.parse_args()

    results = []
    with open(args.results, "r", encoding="utf-8") as f:
        for line in f:
            results.append(json.loads(line))

    if args.limit > 0:
        results = results[:args.limit]

    print(f"Evaluating {len(results)} replies...")

    async with httpx.AsyncClient() as client:
        evals = []
        for i, r in enumerate(results):
            user = r.get("input", "")
            reply = r.get("actual_reply", "")
            case = r.get("case", f"case_{i}")
            if not reply:
                continue
            score = await evaluate_reply(client, user, reply, args.model)
            if "error" in score:
                print(f"  [{case}] eval error: {score['error']}")
                continue
            evals.append({
                "case": case,
                "input": user,
                "reply": reply,
                **score,
            })
            print(f"  [{case}] N={score.get('naturalness')}, W={score.get('warmth')}, U={score.get('undergrad_vibe')}, T={score.get('non_template')}, S={score.get('usefulness')}")

    # Compute averages
    dims = ["naturalness", "warmth", "undergrad_vibe", "non_template", "usefulness"]
    averages = {}
    for dim in dims:
        vals = [e[dim] for e in evals if dim in e and isinstance(e[dim], (int, float))]
        averages[dim] = round(sum(vals) / len(vals), 2) if vals else 0

    # Find low scores
    low_cases = []
    for e in evals:
        for dim in dims:
            val = e.get(dim)
            if isinstance(val, (int, float)) and val < 3:
                low_cases.append({"case": e["case"], "dim": dim, "score": val, "reply": e["reply"]})

    # Find worst traits
    trait_counts = {}
    for e in evals:
        trait = e.get("worst_trait", "none")
        if trait and trait != "none":
            trait_counts[trait] = trait_counts.get(trait, 0) + 1

    # Most psych / customer / robot-like
    psych_cases = sorted([e for e in evals if e.get("undergrad_vibe", 5) < 3], key=lambda x: x.get("undergrad_vibe", 5))
    cust_cases = sorted([e for e in evals if e.get("warmth", 5) < 3], key=lambda x: x.get("warmth", 5))
    robot_cases = sorted([e for e in evals if e.get("non_template", 5) < 3], key=lambda x: x.get("non_template", 5))

    args.out.mkdir(parents=True, exist_ok=True)
    out_path = args.out / "human_likeness_eval.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "averages": averages,
            "low_cases": low_cases,
            "worst_traits": trait_counts,
            "most_psych_counselor": psych_cases[:3],
            "most_customer_service": cust_cases[:3],
            "most_robot": robot_cases[:3],
            "evaluations": evals,
        }, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*50}")
    print("HUMAN LIKENESS EVALUATION RESULTS")
    print(f"{'='*50}")
    print(f"Cases evaluated: {len(evals)}")
    for dim, avg in averages.items():
        print(f"  {dim}: {avg}/5.0")
    print(f"\nLow score cases (< 3): {len(low_cases)}")
    print(f"Worst traits: {trait_counts}")
    print(f"\nMost psych-counselor-like: {[e['case'] for e in psych_cases[:3]]}")
    print(f"Most customer-service-like: {[e['case'] for e in cust_cases[:3]]}")
    print(f"Most robot-like: {[e['case'] for e in robot_cases[:3]]}")
    print(f"\nResults saved to: {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
