#!/usr/bin/env python3
"""
Conversation Self-Evaluator
对长对话日志进行结构化评估。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

DIMS = [
    "naturalness",      # 是否像自然朋友聊天
    "interestingness",  # 是否有趣
    "personalization",  # 是否结合用户具体信息
    "emotional_timing", # 是否知道何时陪伴、何时推进
    "usefulness",       # 是否在需要时有帮助
    "memory_use",       # 是否自然使用记忆
    "non_template",     # 是否避免模板腔
    "brevity_balance",  # 是否短但不空
    "boundary_respect", # 是否尊重不记忆、不分析、不建议
]


def evaluate_turn(turn: dict[str, Any], prev_turns: list[dict[str, Any]]) -> dict[str, Any]:
    """Heuristic evaluation of a single turn."""
    user = turn["user"]
    assistant = turn["assistant"]
    scene = turn.get("scene", "")
    test_mem = turn.get("test_memory", "")

    scores = {}
    notes = []

    # Naturalness: length check + marker words
    if len(assistant) < 5:
        scores["naturalness"] = 2
        notes.append("Too short")
    elif any(m in assistant for m in ["作为AI", "我的职责", "很高兴为您服务"]):
        scores["naturalness"] = 2
        notes.append("Template tone")
    elif ".." in assistant or "..." in assistant or assistant.endswith("。"):
        scores["naturalness"] = 4
    else:
        scores["naturalness"] = 4

    # Interestingness
    funny_markers = ["笑死", "离谱", "阿哲", "yyds", "亲测", "螺蛳粉", "冰美式", "编译器", "发际线"]
    if any(m in assistant for m in funny_markers):
        scores["interestingness"] = 5
    elif len(assistant) < 10:
        scores["interestingness"] = 2
        notes.append("Too short to be interesting")
    elif "懂的" in assistant and len(assistant) < 15:
        scores["interestingness"] = 2
        notes.append("Generic '懂的'")
    else:
        scores["interestingness"] = 3

    # Personalization: check if user-specific info is referenced
    user_names = ["昊文", "林昊文"]
    user_items = ["阿哲", "小满", "Rain", "螺蛳粉", "冰美式", "南宁", "落日飞车", "嵌入式", "presentation", "数字通信", "微波工程"]
    personalized = any(name in assistant for name in user_names) or any(item in assistant for item in user_items)
    if personalized:
        scores["personalization"] = 5
        notes.append(f"Personalized: {', '.join([i for i in user_items if i in assistant])}")
    elif test_mem and "记住" in test_mem:
        scores["personalization"] = 2
        notes.append("Missed personalization opportunity")
    else:
        scores["personalization"] = 3

    # Memory use
    if test_mem and "记住" in test_mem:
        if personalized:
            scores["memory_use"] = 5
        else:
            scores["memory_use"] = 2
            notes.append("Memory not used naturally")
    elif test_mem and "测试" in test_mem:
        scores["memory_use"] = 3 if personalized else 2
    else:
        scores["memory_use"] = 3

    # Emotional timing
    if scene in ["post_exam", "stress", "family"] and any(m in assistant for m in ["抱抱", "懂", "确实", "太真实"]):
        scores["emotional_timing"] = 4
    elif scene == "boundary" and any(m in assistant for m in ["懂了", "好的", "不说"]):
        scores["emotional_timing"] = 4
    else:
        scores["emotional_timing"] = 3

    # Usefulness
    if scene in ["planning", "stress"] and any(m in assistant for m in ["先搞", "试试", "拆成", "列几个"]):
        scores["usefulness"] = 4
    elif scene == "casual":
        scores["usefulness"] = 3
    else:
        scores["usefulness"] = 3

    # Non-template
    template_phrases = ["很高兴认识你", "有什么可以帮您", "建议您", "您可以试试", "首先", "其次", "最后"]
    if any(p in assistant for p in template_phrases):
        scores["non_template"] = 2
        notes.append("Template phrase detected")
    elif ".." in assistant and len(assistant) < 15:
        scores["non_template"] = 3
    else:
        scores["non_template"] = 4

    # Brevity balance
    if len(assistant) < 8:
        scores["brevity_balance"] = 2
        notes.append("Too short")
    elif len(assistant) > 80:
        scores["brevity_balance"] = 3
        notes.append("A bit long")
    else:
        scores["brevity_balance"] = 4

    # Boundary respect
    if scene == "boundary" and any(m in assistant for m in ["分析", "建议", "应该", "为什么"]):
        scores["boundary_respect"] = 2
        notes.append("Boundary violated")
    elif "别记" in user and "懂的" in assistant:
        scores["boundary_respect"] = 5
        notes.append("Respected do-not-remember")
    else:
        scores["boundary_respect"] = 4

    return {"scores": scores, "notes": notes, "overall": round(sum(scores.values()) / len(scores), 2)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    turns = []
    with open(args.log, "r", encoding="utf-8") as f:
        for line in f:
            turns.append(json.loads(line.strip()))

    print(f"Evaluating {len(turns)} turns...")

    evals = []
    for i, turn in enumerate(turns):
        ev = evaluate_turn(turn, turns[:i])
        ev["turn"] = i + 1
        ev["user"] = turn["user"]
        ev["assistant"] = turn["assistant"]
        ev["scene"] = turn.get("scene", "")
        evals.append(ev)
        print(f"  [Turn {i+1}] overall={ev['overall']} | notes={'; '.join(ev['notes'])[:60]}")

    # Aggregate
    dim_avgs = {}
    for dim in DIMS:
        vals = [e["scores"].get(dim, 0) for e in evals if dim in e["scores"]]
        dim_avgs[dim] = round(sum(vals) / len(vals), 2) if vals else 0

    overall_avg = round(sum(e["overall"] for e in evals) / len(evals), 2)

    best = sorted(evals, key=lambda x: x["overall"], reverse=True)[:5]
    worst = sorted(evals, key=lambda x: x["overall"])[:5]

    report = {
        "overall_score": overall_avg,
        "dimension_scores": dim_avgs,
        "turn_evaluations": evals,
        "best_turns": [{"turn": e["turn"], "user": e["user"][:40], "assistant": e["assistant"][:60], "score": e["overall"]} for e in best],
        "worst_turns": [{"turn": e["turn"], "user": e["user"][:40], "assistant": e["assistant"][:60], "score": e["overall"], "notes": e["notes"]} for e in worst],
    }

    args.out.mkdir(parents=True, exist_ok=True)
    out_path = args.out / "self_eval.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*50}")
    print("SELF EVALUATION RESULTS")
    print(f"{'='*50}")
    print(f"Overall: {overall_avg}/5.0")
    for dim, score in dim_avgs.items():
        print(f"  {dim}: {score}/5.0")
    print(f"\nBest turns: {[e['turn'] for e in best]}")
    print(f"Worst turns: {[e['turn'] for e in worst]}")
    print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    main()
