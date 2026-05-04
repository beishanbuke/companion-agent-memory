"""
Chat Quality Runner

批量运行聊天质量测试，保存每条输入、输出、policy、intent、state、memory、tool_calls、stage_timings。

Usage:
    python tests/chat_quality_runner.py

Output:
    tests/chat_quality_results.jsonl
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any

import httpx

PROJECT_DIR = Path(__file__).resolve().parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))


BASE_URL = "http://127.0.0.1:8765"


def load_cases(path: Path) -> list[dict[str, Any]]:
    cases = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            cases.append(json.loads(line))
    return cases


async def run_single_case(
    client: httpx.AsyncClient,
    case: dict[str, Any],
) -> dict[str, Any]:
    """Run a single test case and collect all metadata."""
    payload = {
        "message": case["input"],
        "memory_enabled": True,
        "use_v2_brain": True,
        "debug": True,
    }

    start_time = time.perf_counter()
    try:
        response = await client.post(
            f"{BASE_URL}/api/chat",
            json=payload,
            timeout=60.0,
        )
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        return {
            "case": case["case"],
            "input": case["input"],
            "error": str(exc),
            "passed": False,
        }

    total_time = time.perf_counter() - start_time

    reply = data.get("reply", "")
    companion = data.get("companion", {})
    debug = data.get("debug", {})
    context_meta = data.get("context_meta", {})

    # Extract key debug fields
    intent = debug.get("intent", {})
    state = debug.get("state", {})
    policy = debug.get("policy", {})
    stage_timings = debug.get("stage_timings", {})
    threads = debug.get("threads", {})
    memory_decision = companion.get("memory_decision", {})

    result = {
        "case": case["case"],
        "input": case["input"],
        "expected": case.get("expected", ""),
        "category": case.get("category", ""),
        "tags": case.get("tags", []),
        "reply": reply,
        "reply_length": len(reply),
        "reply_sentence_count": len([s for s in reply.replace("！", "。").replace("？", "。").split("。") if s.strip()]),
        "total_time": round(total_time, 3),
        "intent_primary": intent.get("primary", ""),
        "intent_emotion": intent.get("emotion", ""),
        "intent_rhythm": intent.get("rhythm", ""),
        "state_current": state.get("current_state", ""),
        "policy_goal": policy.get("goal", ""),
        "policy_allow_advice": policy.get("allow_advice", False),
        "policy_allow_humor": policy.get("allow_humor", False),
        "stage_timings": stage_timings,
        "memory_decision_action": memory_decision.get("action", ""),
        "memory_decision_reason": memory_decision.get("reason", ""),
        "active_thread": threads.get("active", {}),
        "background_count": threads.get("background_count", 0),
        "v2_brain": context_meta.get("v2_brain", False),
    }

    return result


async def run_all_cases(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Run all test cases sequentially (to avoid session interference)."""
    async with httpx.AsyncClient() as client:
        results = []
        for case in cases:
            print(f"Running: {case['case']} -> {case['input'][:30]}...")
            result = await run_single_case(client, case)
            results.append(result)
            # Small delay to avoid overwhelming the server
            await asyncio.sleep(0.5)
        return results


def analyze_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Analyze test results and produce summary."""
    total = len(results)
    errors = [r for r in results if "error" in r]
    success = [r for r in results if "error" not in r]

    # Timing stats
    timings = [r["total_time"] for r in success]
    avg_time = sum(timings) / len(timings) if timings else 0
    max_time = max(timings) if timings else 0
    min_time = min(timings) if timings else 0

    # Intent distribution
    intent_counts: dict[str, int] = {}
    for r in success:
        intent = r.get("intent_primary", "unknown")
        intent_counts[intent] = intent_counts.get(intent, 0) + 1

    # Policy goal distribution
    goal_counts: dict[str, int] = {}
    for r in success:
        goal = r.get("policy_goal", "unknown")
        goal_counts[goal] = goal_counts.get(goal, 0) + 1

    # Reply length stats
    lengths = [r.get("reply_length", 0) for r in success]
    avg_length = sum(lengths) / len(lengths) if lengths else 0

    # Stage timing averages
    stage_avgs: dict[str, list[float]] = {}
    for r in success:
        for stage, val in r.get("stage_timings", {}).items():
            if isinstance(val, (int, float)):
                stage_avgs.setdefault(stage, []).append(val)

    stage_avg_summary = {
        stage: round(sum(vals) / len(vals), 3)
        for stage, vals in stage_avgs.items()
    }

    return {
        "total_cases": total,
        "success_count": len(success),
        "error_count": len(errors),
        "avg_response_time": round(avg_time, 3),
        "max_response_time": round(max_time, 3),
        "min_response_time": round(min_time, 3),
        "avg_reply_length": round(avg_length, 1),
        "intent_distribution": intent_counts,
        "policy_goal_distribution": goal_counts,
        "stage_timing_averages": stage_avg_summary,
        "errors": [{"case": r["case"], "error": r["error"]} for r in errors],
    }


def save_results(results: list[dict[str, Any]], summary: dict[str, Any], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    # Save detailed results
    results_path = out_dir / "chat_quality_results.jsonl"
    with open(results_path, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # Save summary
    summary_path = out_dir / "chat_quality_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"\nResults saved to: {results_path}")
    print(f"Summary saved to: {summary_path}")


def print_summary(summary: dict[str, Any]) -> None:
    print("\n" + "=" * 60)
    print("CHAT QUALITY TEST SUMMARY")
    print("=" * 60)
    print(f"Total cases: {summary['total_cases']}")
    print(f"Success: {summary['success_count']} | Errors: {summary['error_count']}")
    print(f"\nTiming:")
    print(f"  Avg: {summary['avg_response_time']}s")
    print(f"  Max: {summary['max_response_time']}s")
    print(f"  Min: {summary['min_response_time']}s")
    print(f"\nReply length: avg {summary['avg_reply_length']} chars")
    print(f"\nIntent distribution:")
    for intent, count in sorted(summary['intent_distribution'].items(), key=lambda x: -x[1]):
        print(f"  {intent}: {count}")
    print(f"\nPolicy goal distribution:")
    for goal, count in sorted(summary['policy_goal_distribution'].items(), key=lambda x: -x[1]):
        print(f"  {goal}: {count}")
    print(f"\nStage timing averages:")
    for stage, avg in sorted(summary['stage_timing_averages'].items(), key=lambda x: x[0]):
        print(f"  {stage}: {avg}s")
    if summary['errors']:
        print(f"\nErrors:")
        for e in summary['errors']:
            print(f"  {e['case']}: {e['error']}")
    print("=" * 60)


def main() -> None:
    parser = argparse.ArgumentParser(description="Chat Quality Runner")
    parser.add_argument("--cases", type=Path, default=PROJECT_DIR / "tests" / "chat_quality_cases.jsonl")
    parser.add_argument("--out", type=Path, default=PROJECT_DIR / "tests" / "chat_quality_results")
    parser.add_argument("--url", default=BASE_URL)
    args = parser.parse_args()

    global BASE_URL
    BASE_URL = args.url

    cases = load_cases(args.cases)
    print(f"Loaded {len(cases)} test cases from {args.cases}")

    results = asyncio.run(run_all_cases(cases))
    summary = analyze_results(results)

    save_results(results, summary, args.out)
    print_summary(summary)


if __name__ == "__main__":
    main()
