"""
Chat Quality Runner

批量运行聊天质量测试，保存每条输入、输出、policy、intent、state、memory、tool_calls、stage_timings。
新增：hard_rules / FAILURE_FLAGS 检查，PASS/FAIL 判定，quality_flags 分类统计。

Usage:
    python tests/chat_quality_runner.py

Output:
    tests/chat_quality_results.jsonl
    tests/chat_quality_summary.json
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

# ---------------------------------------------------------------------------
# Quality flag categories
# ---------------------------------------------------------------------------

FAILURE_FLAGS_CATEGORIES = [
    "too_long",
    "too_many_sentences",
    "template_tone",
    "advice_when_should_not",
    "asked_question_when_quiet",
    "fast_path_too_slow",
    "food_reply_too_long",
    "abrupt_thread_pull",
    "missing_safety_action",
    "over_explained_skill",
    "debug_missing_policy",
    "legacy_chain_used",
]


def load_cases(path: Path) -> list[dict[str, Any]]:
    cases = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            cases.append(json.loads(line))
    return cases


def check_response(reply: str, case: dict[str, Any]) -> dict[str, Any]:
    """Check reply against hard_rules (forbidden substrings) and FAILURE_FLAGS."""
    hard_rules = case.get("hard_rules", [])
    failure_flags = case.get("FAILURE_FLAGS", [])
    hard_rules_dict = case.get("hard_rules_dict", {})

    hard_rules_violated = []
    for rule in hard_rules:
        if rule in reply:
            hard_rules_violated.append(rule)

    failure_flags_found = []
    for flag in failure_flags:
        if flag in reply:
            failure_flags_found.append(flag)

    # hard_rules_dict checks
    quality_flags: list[str] = []
    if hard_rules_dict:
        max_sentences = hard_rules_dict.get("max_sentences")
        if max_sentences is not None:
            sentences = len([s for s in reply.replace("！", "。").replace("？", "。").split("。") if s.strip()])
            if sentences > max_sentences:
                quality_flags.append("too_many_sentences")
        max_questions = hard_rules_dict.get("max_questions")
        if max_questions is not None:
            questions = reply.count("?") + reply.count("？")
            if questions > max_questions:
                quality_flags.append("asked_question_when_quiet")
        allow_advice = hard_rules_dict.get("allow_advice")
        if allow_advice is False:
            advice_markers = ["建议", "你可以", "你应该", "试试", "方案"]
            if any(m in reply for m in advice_markers):
                quality_flags.append("advice_when_should_not")
        pull_mode = hard_rules_dict.get("pull_mode")
        if pull_mode == "silent":
            pull_markers = ["不过你之前", "但是你还有", "别忘了你", "你之前说"]
            if any(m in reply for m in pull_markers):
                quality_flags.append("abrupt_thread_pull")

    # Template tone detection (heuristic)
    template_markers = ["首先", "其次", "最后", "综上所述", "总结一下", "我理解你的感受"]
    if any(m in reply for m in template_markers):
        quality_flags.append("template_tone")

    # Too long heuristic
    if len(reply) > 120:
        quality_flags.append("too_long")

    # Food reply too long
    if case.get("category") == "food" and len(reply) > 60:
        quality_flags.append("food_reply_too_long")

    passed = (
        len(hard_rules_violated) == 0
        and len(failure_flags_found) == 0
        and len(quality_flags) == 0
    )
    reasons: list[str] = []
    if hard_rules_violated:
        reasons.append(f"Hard rules violated: {hard_rules_violated}")
    if failure_flags_found:
        reasons.append(f"Failure flags found: {failure_flags_found}")
    if quality_flags:
        reasons.append(f"Quality flags: {quality_flags}")

    return {
        "hard_rules_violated": hard_rules_violated,
        "failure_flags_found": failure_flags_found,
        "quality_flags": quality_flags,
        "passed": passed,
        "reason": "; ".join(reasons) if reasons else "No violations",
    }


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
            "expected_style": case.get("expected_style", case.get("expected", "")),
            "actual_reply": "",
            "error": str(exc),
            "hard_rules_violated": [],
            "failure_flags_found": [],
            "quality_flags": [],
            "passed": False,
            "reason": f"HTTP/Connection error: {exc}",
            "timing_ms": 0,
        }

    total_time = time.perf_counter() - start_time
    timing_ms = round(total_time * 1000, 1)

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

    # Run quality checks
    check = check_response(reply, case)

    result = {
        # Required output fields
        "input": case["input"],
        "expected_style": case.get("expected_style", case.get("expected", "")),
        "actual_reply": reply,
        "hard_rules_violated": check["hard_rules_violated"],
        "failure_flags_found": check["failure_flags_found"],
        "quality_flags": check["quality_flags"],
        "timing_ms": timing_ms,
        # PASS/FAIL
        "passed": check["passed"],
        "pass_fail_reason": check["reason"],
        # Legacy / detailed fields
        "case": case["case"],
        "category": case.get("category", ""),
        "tags": case.get("tags", []),
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
        "policy_pull_mode": policy.get("pull_mode", ""),
        "policy_skill_verbosity": policy.get("skill_verbosity", ""),
        "stage_timings": stage_timings,
        "memory_decision_action": memory_decision.get("action", ""),
        "memory_decision_reason": memory_decision.get("reason", ""),
        "active_thread": threads.get("active", {}),
        "background_count": threads.get("background_count", 0),
        "v2_brain": context_meta.get("v2_brain", False),
        "legacy_fallback_used": context_meta.get("legacy_fallback_used", False),
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

            # Print PASS/FAIL per case
            status = "PASS" if result.get("passed") else "FAIL"
            reason = result.get("pass_fail_reason", "")
            print(f"  [{status}] {reason}")

            # Small delay to avoid overwhelming the server
            await asyncio.sleep(0.5)
        return results


def analyze_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Analyze test results and produce summary."""
    total = len(results)
    errors = [r for r in results if "error" in r]
    success = [r for r in results if "error" not in r]

    # Timing stats
    timings = [r["timing_ms"] for r in success]
    avg_time_ms = sum(timings) / len(timings) if timings else 0
    max_time_ms = max(timings) if timings else 0
    min_time_ms = min(timings) if timings else 0

    # PASS/FAIL stats
    passed_cases = [r for r in success if r.get("passed")]
    failed_cases = [r for r in success if not r.get("passed")]

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

    # Failure analysis by raw reason
    failure_reasons: dict[str, int] = {}
    for r in failed_cases:
        reason = r.get("pass_fail_reason", "")
        failure_reasons[reason] = failure_reasons.get(reason, 0) + 1

    # Failure distribution by quality_flag
    failure_distribution: dict[str, int] = {}
    for r in failed_cases:
        for flag in r.get("quality_flags", []):
            failure_distribution[flag] = failure_distribution.get(flag, 0) + 1
        for flag in r.get("hard_rules_violated", []):
            key = f"hard_rule:{flag}"
            failure_distribution[key] = failure_distribution.get(key, 0) + 1
        for flag in r.get("failure_flags_found", []):
            key = f"failure_flag:{flag}"
            failure_distribution[key] = failure_distribution.get(key, 0) + 1

    return {
        "total_cases": total,
        "success_count": len(success),
        "error_count": len(errors),
        "pass_count": len(passed_cases),
        "fail_count": len(failed_cases),
        "pass_rate": round(len(passed_cases) / len(success), 2) if success else 0,
        "avg_response_time_ms": round(avg_time_ms, 1),
        "max_response_time_ms": round(max_time_ms, 1),
        "min_response_time_ms": round(min_time_ms, 1),
        "avg_reply_length": round(avg_length, 1),
        "intent_distribution": intent_counts,
        "policy_goal_distribution": goal_counts,
        "stage_timing_averages": stage_avg_summary,
        "failure_distribution": failure_distribution,
        "errors": [{"case": r["case"], "error": r["error"]} for r in errors],
        "failures": [
            {
                "case": r["case"],
                "input": r["input"],
                "reason": r.get("pass_fail_reason", ""),
                "hard_rules_violated": r.get("hard_rules_violated", []),
                "failure_flags_found": r.get("failure_flags_found", []),
                "quality_flags": r.get("quality_flags", []),
            }
            for r in failed_cases
        ],
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
    print(f"PASS: {summary['pass_count']} | FAIL: {summary['fail_count']} (rate: {summary['pass_rate']})")
    print(f"\nTiming:")
    print(f"  Avg: {summary['avg_response_time_ms']}ms")
    print(f"  Max: {summary['max_response_time_ms']}ms")
    print(f"  Min: {summary['min_response_time_ms']}ms")
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
    if summary['failures']:
        print(f"\nFailures ({len(summary['failures'])}):")
        for f in summary['failures']:
            print(f"  {f['case']}: {f['reason']}")
    if summary.get("failure_distribution"):
        print(f"\nFailure distribution:")
        for flag, count in sorted(summary['failure_distribution'].items(), key=lambda x: -x[1]):
            print(f"  {flag}: {count}")
    print("=" * 60)


def main() -> None:
    parser = argparse.ArgumentParser(description="Chat Quality Runner")
    parser.add_argument("--cases", type=Path, default=PROJECT_DIR / "tests" / "chat_quality_cases.jsonl")
    parser.add_argument("--out", type=Path, default=PROJECT_DIR / "tests" / "chat_quality_results")
    parser.add_argument("--url", default=None)
    parser.add_argument("--threshold", type=float, default=0.90, help="Minimum pass rate (default 0.90)")
    args = parser.parse_args()

    global BASE_URL
    if args.url:
        BASE_URL = args.url

    cases = load_cases(args.cases)
    print(f"Loaded {len(cases)} test cases from {args.cases}")

    results = asyncio.run(run_all_cases(cases))
    summary = analyze_results(results)

    save_results(results, summary, args.out)
    print_summary(summary)

    if summary["pass_rate"] < args.threshold:
        print(f"\n❌ PASS RATE {summary['pass_rate']} < threshold {args.threshold}")
        sys.exit(1)
    print(f"\n✅ PASS RATE {summary['pass_rate']} >= threshold {args.threshold}")


if __name__ == "__main__":
    main()
