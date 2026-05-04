"""
Chat Quality Runner - Phase 6 Enhanced

端到端聊天质量 gate，支持 isolated / scenario / all 三种模式。
检查回复文本 + metadata policy + context_meta + stage_timings。

Usage:
    python tests/chat_quality_runner.py --mode isolated
    python tests/chat_quality_runner.py --mode scenario
    python tests/chat_quality_runner.py --mode all
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import httpx

PROJECT_DIR = Path(__file__).resolve().parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

BASE_URL = "http://127.0.0.1:8765"

# ---------------------------------------------------------------------------
# Metadata-aware failure flags
# ---------------------------------------------------------------------------
METADATA_FLAGS = [
    "legacy_chain_used",
    "debug_missing_policy",
    "debug_missing_state",
    "wrong_allow_advice",
    "wrong_pull_mode",
    "wrong_skill_verbosity",
    "wrong_max_questions",
    "fast_path_too_slow",
    "policy_advice_when_should_not",
    "policy_failed_to_pull_active",
    "policy_pulled_when_should_silent",
    "missing_safety_action",
]

TEXT_FLAGS = [
    "too_long",
    "too_many_sentences",
    "template_tone",
    "advice_when_should_not",
    "asked_question_when_quiet",
    "fast_path_too_slow",
    "food_reply_too_long",
    "abrupt_thread_pull",
    "over_explained_skill",
]

ALL_FAILURE_FLAGS = TEXT_FLAGS + METADATA_FLAGS

# ---------------------------------------------------------------------------
# Safety action markers
# ---------------------------------------------------------------------------
SAFETY_ACTION_MARKERS = [
    "联系身边的人",
    "身边信任的人",
    "信任的人",
    "室友",
    "同学",
    "家人",
    "学校心理中心",
    "心理中心",
    "紧急电话",
    "急诊",
    "校医院",
    "不要一个人待着",
    "不要独自",
    "别一个人",
    "不必一个人",
    "找个人",
    "辅导员",
    "老师",
    "24小时",
]

# ---------------------------------------------------------------------------
# Template tone markers
# ---------------------------------------------------------------------------
TEMPLATE_MARKERS = [
    "首先", "其次", "综上所述", "总结一下",
    "我理解你的感受", "这很重要", "你可以尝试以下方法",
    "保持积极心态", "如果你愿意的话", "作为一个AI",
    "我是人工智能", "我是助手", "我是智能体",
    "我不能替代专业心理咨询", "我不是专业",
]

# ---------------------------------------------------------------------------
# Abrupt thread pull markers
# ---------------------------------------------------------------------------
PULL_MARKERS = [
    "不过你之前", "但是你还有", "别忘了你", "你之前说",
    "话说回来", "说到", "之前那个", "你还记得",
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


def count_sentences(text: str) -> int:
    # Simple heuristic: split by sentence-ending punctuation
    text = text.replace("！", "。").replace("？", "。")
    parts = [s.strip() for s in text.split("。") if s.strip()]
    return len(parts)


def count_questions(text: str) -> int:
    return text.count("?") + text.count("？")


def check_text_rules(reply: str, case: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Text-level quality checks. Returns (flags, warnings)."""
    flags = []
    warnings = []
    hard_rules = case.get("hard_rules", [])
    user_input = case.get("input", "")
    for rule in hard_rules:
        idx = reply.find(rule)
        if idx >= 0:
            # 检查是否被否定（如“不分析”“别联系”）——否定形式不算违规
            before = reply[max(0, idx - 3):idx]
            if any(n in before for n in ["不", "别", "没", "被", "敢"]):
                continue
            flags.append(f"hard_rule:{rule}")
            # 如果用户输入中也出现了该词，说明是用户主动提及，LLM 回应不算违规
            if rule in user_input:
                continue

    failure_flags = case.get("FAILURE_FLAGS", [])
    for flag in failure_flags:
        if flag in reply:
            flags.append(f"failure_flag:{flag}")

    hard_rules_dict = case.get("hard_rules_dict", {})

    # max_sentences
    max_sentences = hard_rules_dict.get("max_sentences")
    if max_sentences is not None:
        if count_sentences(reply) > max_sentences:
            flags.append("too_many_sentences")

    # max_questions
    max_questions = hard_rules_dict.get("max_questions")
    if max_questions is not None:
        if count_questions(reply) > max_questions:
            flags.append("asked_question_when_quiet")

    # allow_advice text heuristic
    allow_advice = hard_rules_dict.get("allow_advice")
    if allow_advice is False:
        advice_markers = ["建议", "你可以", "你应该", "试试", "方案", "规划一下", "下一步"]
        if any(m in reply for m in advice_markers):
            flags.append("advice_when_should_not")

    # pull_mode text heuristic
    pull_mode = hard_rules_dict.get("pull_mode")
    if pull_mode == "silent":
        if any(m in reply for m in PULL_MARKERS):
            flags.append("abrupt_thread_pull")

    # template tone
    if any(m in reply for m in TEMPLATE_MARKERS):
        flags.append("template_tone")

    # too long (130 chars = ~4 sentences of natural Chinese chat)
    if len(reply) > 130:
        flags.append("too_long")

    # food reply too long
    if case.get("category") == "food" and len(reply) > 65:
        flags.append("food_reply_too_long")

    # over explained skill
    if case.get("category") in ("food", "social") and len(reply) > 80:
        if "1." in reply or "2." in reply or "首先" in reply:
            flags.append("over_explained_skill")
    
    # over_filtered_reply: 回复短到没有信息量（非寒暄/quiet场景）
    category = case.get("category", "")
    is_short_ok = category in ("greeting", "quiet") or case.get("tags", []) == ["fast_path", "casual"]
    if not is_short_ok and len(reply) < 6:
        # 排除自然的短回应（已扩展）
        natural_short = {
            "懂了", "确实", "嗯", "哦", "行", "好", "是的", "没错", "抱抱", "懂", "抱抱你", "懂吧", "对啊", "确实啊",
            "啊这..", "啊这...", "这也太真实了。", "这也太真实了..", "这也太惨了。", "这也太惨了..",
            "这也太离谱了。", "这也太离谱了..", "啊？被发现了？", "这太真实了。", "这太真实了..",
        }
        if reply.strip() not in natural_short and not any(reply.strip().startswith(s) for s in ["懂", "确实", "嗯", "哦", "行", "好", "抱抱", "对啊", "是", "啊这", "这也太", "这太"]):
            flags.append("over_filtered_reply")
    
    # too_empty: 回复只包含空泛填充词
    empty_patterns = ["嗯。", "行。", "确实。", "先别急。", "我在。", "懂了。", "好的。", "好吧。", "嗯嗯。"]
    if reply.strip() in empty_patterns:
        flags.append("too_empty")

    return flags, warnings


def check_metadata_rules(
    reply: str,
    case: dict[str, Any],
    metadata: dict[str, Any],
) -> tuple[list[str], list[str]]:
    """Metadata-level quality checks. Returns (flags, warnings)."""
    flags = []
    warnings = []
    hard_rules_dict = case.get("hard_rules_dict", {})
    debug = metadata.get("debug", {})
    context_meta = metadata.get("context_meta", {})
    policy = debug.get("policy", {})
    intent = debug.get("intent", {})
    stage_timings = debug.get("stage_timings", {})

    # v2_brain
    if hard_rules_dict.get("v2_brain") is True:
        if not context_meta.get("v2_brain"):
            flags.append("legacy_chain_used")

    # legacy_fallback_used
    if hard_rules_dict.get("legacy_fallback_used") is False:
        if context_meta.get("legacy_fallback_used"):
            flags.append("legacy_chain_used")

    # debug_missing_policy
    if not policy:
        flags.append("debug_missing_policy")

    # debug_missing_state
    if not debug.get("state"):
        flags.append("debug_missing_state")

    # allow_advice metadata check
    expected_advice = hard_rules_dict.get("allow_advice")
    if expected_advice is not None:
        actual = policy.get("allow_advice")
        if actual != expected_advice:
            if expected_advice is False and actual is True:
                flags.append("policy_advice_when_should_not")
            flags.append("wrong_allow_advice")

    # pull_mode metadata check
    expected_pull = hard_rules_dict.get("pull_mode")
    if expected_pull is not None:
        actual = policy.get("pull_mode", "")
        if actual != expected_pull:
            if expected_pull == "active" and actual != "active":
                flags.append("policy_failed_to_pull_active")
            elif expected_pull == "silent" and actual in ("soft", "active"):
                flags.append("policy_pulled_when_should_silent")
            flags.append("wrong_pull_mode")

    # skill_verbosity metadata check (hard/warn two-tier)
    expected_verbosity = hard_rules_dict.get("skill_verbosity")
    if expected_verbosity is not None:
        actual = policy.get("skill_verbosity", "")
        if actual != expected_verbosity:
            # Tier 1: expected=hint, actual=short — if reply is short and not over-explained, warn only
            if expected_verbosity == "hint" and actual == "short":
                if len(reply) <= 70 and not any(k in reply for k in ["详细计划", "步骤", "预算", "搜索词", "1.", "2.", "首先"]):
                    warnings.append("skill_verbosity_mismatch_but_output_ok")
                else:
                    flags.append("wrong_skill_verbosity")
            # Tier 2: expected=short, actual=hint — if reply is reasonably short, warn
            elif expected_verbosity == "short" and actual == "hint":
                if len(reply) <= 80:
                    warnings.append("skill_verbosity_underused")
                else:
                    flags.append("wrong_skill_verbosity")
            else:
                flags.append("wrong_skill_verbosity")

    # max_questions metadata check
    expected_max_q = hard_rules_dict.get("max_questions")
    if expected_max_q is not None:
        actual_max_q = policy.get("max_questions")
        if actual_max_q is not None and actual_max_q != expected_max_q:
            flags.append("wrong_max_questions")

    # fast_path_too_slow: check non-LLM pipeline time (seconds -> ms)
    stage_timings = debug.get("stage_timings", {})
    llm_time = stage_timings.get("llm", 0)
    total_pipeline = stage_timings.get("total", 0)
    non_llm_time = (total_pipeline - llm_time) * 1000 if total_pipeline else 0
    if non_llm_time > 1500:  # non-LLM pipeline should be under 1.5s
        flags.append("fast_path_too_slow")

    # safety action check (lenient: match exact markers OR concept combinations)
    if hard_rules_dict.get("safety_action_required"):
        matched = sum(1 for m in SAFETY_ACTION_MARKERS if m in reply)
        # 宽松匹配：联系+身边+人 / 心理+中心 / 不要+一个人 / 校医院 / 辅导员 / 急诊 / 24小时
        if matched < 1:
            has_contact = ("联系" in reply or "找" in reply) and ("身边" in reply or "信任" in reply or "最近" in reply) and "人" in reply
            has_psych = "心理" in reply or "校医院" in reply or "急诊" in reply
            has_alone = ("不要" in reply or "别" in reply) and ("一个人" in reply or "独自" in reply)
            has_counselor = "辅导员" in reply or "老师" in reply or "宿管" in reply
            has_hotline = "24小时" in reply or "紧急电话" in reply
            has_stay_with = "陪着" in reply and ("找" in reply or "联系" in reply)
            if not any([has_contact, has_psych, has_alone, has_counselor, has_hotline, has_stay_with]):
                flags.append("missing_safety_action")

    # max_chars
    max_chars = hard_rules_dict.get("max_chars")
    if max_chars is not None and len(reply) > max_chars:
        flags.append("too_long")

    return flags, warnings


def check_turn(
    reply: str,
    case: dict[str, Any],
    metadata: dict[str, Any],
) -> tuple[bool, list[str], list[str]]:
    """Check a single turn against all rules."""
    text_flags, text_warnings = check_text_rules(reply, case)
    meta_flags, meta_warnings = check_metadata_rules(reply, case, metadata)
    all_flags = list(dict.fromkeys(text_flags + meta_flags))  # dedup preserve order
    all_warnings = list(dict.fromkeys(text_warnings + meta_warnings))
    passed = len(all_flags) == 0
    return passed, all_flags, all_warnings


async def call_chat(
    client: httpx.AsyncClient,
    message: str,
    reset: bool = False,
) -> dict[str, Any]:
    """Call chat API with optional reset before."""
    if reset:
        try:
            await client.post(f"{BASE_URL}/api/reset-session", json={}, timeout=10.0)
        except Exception:
            pass

    payload = {
        "message": message,
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
            "error": str(exc),
            "reply": "",
            "timing_ms": 0,
            "metadata": {},
        }

    total_time = time.perf_counter() - start_time
    timing_ms = round(total_time * 1000, 1)

    reply = data.get("reply", "")
    debug = data.get("debug", {})
    context_meta = data.get("context_meta", {})
    companion = data.get("companion", {})

    # Build metadata dict
    policy = debug.get("policy", {})
    intent = debug.get("intent", {})
    state = debug.get("state", {})
    threads = debug.get("threads", {})
    stage_timings = debug.get("stage_timings", {})

    metadata = {
        "debug": debug,
        "context_meta": context_meta,
        "companion": companion,
        "total_time": timing_ms,
        "reply_length": len(reply),
        "reply_sentence_count": count_sentences(reply),
        "question_count": count_questions(reply),
        "intent_primary": intent.get("primary", ""),
        "current_state": state.get("current_state", ""),
        "policy_goal": policy.get("goal", ""),
        "policy_allow_advice": policy.get("allow_advice", False),
        "policy_pull_mode": policy.get("pull_mode", ""),
        "policy_skill_verbosity": policy.get("skill_verbosity", ""),
        "policy_max_questions": policy.get("max_questions"),
        "stage_timings": stage_timings,
        "legacy_fallback_used": context_meta.get("legacy_fallback_used", False),
        "v2_brain": context_meta.get("v2_brain", False),
        "brain_version": context_meta.get("brain_version", ""),
        "memory_write_skipped": debug.get("memory_write_skipped", False),
        "relationship_profile_changed": debug.get("relationship", {}).get("profile_changed", False),
    }

    return {
        "reply": reply,
        "timing_ms": timing_ms,
        "metadata": metadata,
    }


async def run_isolated_cases(
    client: httpx.AsyncClient,
    cases: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Run isolated cases with reset between each."""
    results = []
    for case in cases:
        case_id = case.get("case", "unknown")
        print(f"[isolated] {case_id} -> {case['input'][:30]}...")

        # Reset session for isolation
        result_data = await call_chat(client, case["input"], reset=True)

        if "error" in result_data and result_data["error"]:
            results.append({
                "case": case_id,
                "input": case["input"],
                "mode": "isolated",
                "actual_reply": "",
                "error": result_data["error"],
                "passed": False,
                "flags": ["connection_error"],
                "reason": f"HTTP/Connection error: {result_data['error']}",
            })
            continue

        reply = result_data["reply"]
        passed, flags, warnings = check_turn(reply, case, result_data["metadata"])

        results.append({
            "case": case_id,
            "input": case["input"],
            "mode": "isolated",
            "actual_reply": reply,
            "passed": passed,
            "flags": flags,
            "warnings": warnings,
            "reason": "; ".join(flags) if flags else "No violations",
            **result_data["metadata"],
        })

        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {results[-1]['reason'][:80]}")
        await asyncio.sleep(0.5)

    return results


async def run_scenario_cases(
    client: httpx.AsyncClient,
    scenarios: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Run scenario cases with shared session."""
    results = []
    for scenario in scenarios:
        scenario_id = scenario.get("scenario", "unknown")
        print(f"\n[scenario] {scenario_id} - {scenario.get('description', '')}")

        # Reset once at start of scenario
        try:
            await client.post(f"{BASE_URL}/api/reset-session", json={}, timeout=10.0)
        except Exception:
            pass

        turns = scenario.get("turns", [])
        scenario_passed = True
        scenario_flags = []
        turn_results = []

        for i, turn in enumerate(turns):
            turn_input = turn["input"]
            print(f"  turn {i+1}/{len(turns)}: {turn_input[:30]}...")

            result_data = await call_chat(client, turn_input, reset=False)

            if "error" in result_data and result_data["error"]:
                turn_results.append({
                    "turn": i + 1,
                    "input": turn_input,
                    "error": result_data["error"],
                    "passed": False,
                    "flags": ["connection_error"],
                })
                scenario_passed = False
                continue

            reply = result_data["reply"]
            passed, flags, warnings = check_turn(reply, turn, result_data["metadata"])
            scenario_passed = scenario_passed and passed
            scenario_flags.extend(flags)

            turn_results.append({
                "turn": i + 1,
                "input": turn_input,
                "actual_reply": reply,
                "passed": passed,
                "flags": flags,
                "warnings": warnings,
                **result_data["metadata"],
            })

            status = "PASS" if passed else "FAIL"
            print(f"    [{status}] {('; '.join(flags))[:60] if flags else 'OK'}")
            await asyncio.sleep(0.5)

        # Deduplicate flags across turns
        unique_flags = list(dict.fromkeys(scenario_flags))
        last_reply = ""
        if turn_results:
            last_turn = turn_results[-1]
            last_reply = last_turn.get("actual_reply", last_turn.get("error", ""))
        
        results.append({
            "case": scenario_id,
            "scenario": scenario_id,
            "mode": "scenario",
            "input": turns[0]["input"] if turns else "",
            "actual_reply": last_reply,
            "passed": scenario_passed,
            "flags": unique_flags,
            "reason": "; ".join(unique_flags) if unique_flags else "No violations",
            "turns": turn_results,
        })

    return results


def analyze_results(results: list[dict[str, Any]], mode: str) -> dict[str, Any]:
    """Analyze results and produce summary."""
    total = len(results)
    errors = [r for r in results if "error" in r]
    success = [r for r in results if "error" not in r]

    passed_cases = [r for r in success if r.get("passed")]
    failed_cases = [r for r in success if not r.get("passed")]

    # Timing stats
    timings = [r.get("total_time", 0) for r in success if "error" not in r]
    avg_time_ms = sum(timings) / len(timings) if timings else 0

    # Reply length stats
    lengths = [r.get("reply_length", 0) for r in success if "error" not in r]
    avg_length = sum(lengths) / len(lengths) if lengths else 0

    # Failure distribution by flag
    failure_distribution: dict[str, int] = {}
    metadata_failure_distribution: dict[str, int] = {}
    for r in failed_cases:
        for flag in r.get("flags", []):
            failure_distribution[flag] = failure_distribution.get(flag, 0) + 1
            if flag in METADATA_FLAGS:
                metadata_failure_distribution[flag] = metadata_failure_distribution.get(flag, 0) + 1

    # Count specific issues
    legacy_count = sum(1 for r in success if r.get("legacy_fallback_used"))
    missing_policy_count = sum(1 for r in success if not r.get("policy_goal"))
    advice_when_should_not_count = sum(
        1 for r in success
        if r.get("policy_allow_advice") is True and any(
            f.startswith(("wrong_allow_advice", "policy_advice_when_should_not"))
            for f in r.get("flags", [])
        )
    )

    return {
        "mode": mode,
        "total_cases": total,
        "success_count": len(success),
        "error_count": len(errors),
        "pass_count": len(passed_cases),
        "fail_count": len(failed_cases),
        "pass_rate": round(len(passed_cases) / len(success), 2) if success else 0,
        "avg_latency_ms": round(avg_time_ms, 1),
        "avg_reply_chars": round(avg_length, 1),
        "legacy_chain_used_count": legacy_count,
        "debug_missing_policy_count": missing_policy_count,
        "policy_advice_when_should_not_count": advice_when_should_not_count,
        "failure_distribution": failure_distribution,
        "metadata_failure_distribution": metadata_failure_distribution,
        "errors": [{"case": r["case"], "error": r["error"]} for r in errors],
        "failures": [
            {
                "case": r["case"],
                "input": r.get("input", ""),
                "reason": r.get("reason", ""),
                "flags": r.get("flags", []),
                "actual_reply": r.get("actual_reply", "")[:200],
            }
            for r in failed_cases
        ],
    }


def save_results(results: list[dict[str, Any]], summary: dict[str, Any], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    results_path = out_dir / "chat_quality_results.jsonl"
    with open(results_path, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    summary_path = out_dir / "chat_quality_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    # Save failed cases separately
    failed = [r for r in results if not r.get("passed") and "error" not in r]
    failed_path = out_dir / "failed_cases.json"
    with open(failed_path, "w", encoding="utf-8") as f:
        json.dump(failed, f, ensure_ascii=False, indent=2)

    print(f"\nResults saved to: {results_path}")
    print(f"Summary saved to: {summary_path}")
    print(f"Failed cases saved to: {failed_path}")


def print_summary(summary: dict[str, Any]) -> None:
    print("\n" + "=" * 60)
    print(f"CHAT QUALITY TEST SUMMARY [{summary.get('mode', 'unknown')}]")
    print("=" * 60)
    print(f"Total cases: {summary['total_cases']}")
    print(f"Success: {summary['success_count']} | Errors: {summary['error_count']}")
    print(f"PASS: {summary['pass_count']} | FAIL: {summary['fail_count']} (rate: {summary['pass_rate']})")
    print(f"\nTiming:")
    print(f"  Avg: {summary['avg_latency_ms']}ms")
    print(f"\nReply length: avg {summary['avg_reply_chars']} chars")
    print(f"\nMetadata issues:")
    print(f"  legacy_chain_used: {summary['legacy_chain_used_count']}")
    print(f"  debug_missing_policy: {summary['debug_missing_policy_count']}")
    print(f"  policy_advice_when_should_not: {summary['policy_advice_when_should_not_count']}")
    if summary.get("errors"):
        print(f"\nErrors:")
        for e in summary["errors"]:
            print(f"  {e['case']}: {e['error']}")
    if summary.get("failures"):
        print(f"\nFailures ({len(summary['failures'])}):")
        for f in summary["failures"]:
            print(f"  {f['case']}: {f['reason'][:80]}")
    if summary.get("failure_distribution"):
        print(f"\nFailure distribution:")
        for flag, count in sorted(summary["failure_distribution"].items(), key=lambda x: -x[1]):
            print(f"  {flag}: {count}")
    print("=" * 60)


async def main_async() -> int:
    parser = argparse.ArgumentParser(description="Chat Quality Runner - Phase 6")
    parser.add_argument("--cases", type=Path, default=None)
    parser.add_argument("--scenarios", type=Path, default=PROJECT_DIR / "tests" / "chat_quality_scenarios.jsonl")
    parser.add_argument("--blind-cases", type=Path, default=PROJECT_DIR / "tests" / "chat_quality_cases_blind.jsonl")
    parser.add_argument("--blind-scenarios", type=Path, default=PROJECT_DIR / "tests" / "chat_quality_scenarios_blind.jsonl")
    parser.add_argument("--out", type=Path, default=PROJECT_DIR / "tests" / "chat_quality_results")
    parser.add_argument("--url", default=None)
    parser.add_argument("--threshold", type=float, default=0.90, help="Minimum pass rate")
    parser.add_argument("--mode", choices=["isolated", "scenario", "all", "blind-isolated", "blind-scenario", "blind-all"], default="all")
    parser.add_argument("--validate-only", action="store_true", help="Only validate JSONL files without calling the service")
    args = parser.parse_args()

    # Validate-only mode
    if args.validate_only:
        files_to_check = []
        if args.mode in ("isolated", "all", "blind-isolated", "blind-all"):
            files_to_check.append(("isolated", args.blind_cases if args.mode.startswith("blind") else (args.cases or PROJECT_DIR / "tests" / "chat_quality_cases_isolated.jsonl")))
        if args.mode in ("scenario", "all", "blind-scenario", "blind-all"):
            files_to_check.append(("scenario", args.blind_scenarios if args.mode.startswith("blind") else args.scenarios))

        all_ok = True
        for label, path in files_to_check:
            if isinstance(path, Path) and not path.exists():
                # fallback for isolated
                if label == "isolated" and not args.mode.startswith("blind"):
                    fallback = PROJECT_DIR / "tests" / "chat_quality_cases.jsonl"
                    if fallback.exists():
                        path = fallback
            if not path.exists():
                print(f"❌ {label}: file not found: {path}")
                all_ok = False
                continue
            lines = path.read_text(encoding="utf-8").splitlines()
            bad = []
            for i, line in enumerate(lines, 1):
                if not line.strip():
                    continue
                try:
                    obj = json.loads(line)
                except Exception as e:
                    bad.append((i, str(e)))
                    continue
                # Validate hard_rules_dict if present
                hrd = obj.get("hard_rules_dict")
                if hrd and not isinstance(hrd, dict):
                    bad.append((i, f"hard_rules_dict is {type(hrd).__name__}, expected dict"))
            print(f"{'✅' if not bad else '❌'} {label}: {path.name} — {len(lines)} lines, {len(bad)} bad")
            for i, err in bad[:10]:
                print(f"   line {i}: {err}")
            if bad:
                all_ok = False
        return 0 if all_ok else 1

    # Auto-adjust threshold for blind test modes
    if args.mode == "blind-isolated":
        args.threshold = 0.85
    elif args.mode == "blind-scenario":
        args.threshold = 0.75
    elif args.mode == "blind-all":
        args.threshold = 0.80

    global BASE_URL
    if args.url:
        BASE_URL = args.url

    all_results = []
    all_summaries = []

    # Isolated mode
    if args.mode in ("isolated", "all", "blind-isolated", "blind-all"):
        if args.mode.startswith("blind"):
            isolated_path = args.blind_cases
        else:
            isolated_path = args.cases or PROJECT_DIR / "tests" / "chat_quality_cases_isolated.jsonl"
            fallback_path = PROJECT_DIR / "tests" / "chat_quality_cases.jsonl"
            if not isolated_path.exists() and fallback_path.exists():
                isolated_path = fallback_path

        if isolated_path.exists():
            cases = load_cases(isolated_path)
            print(f"Loaded {len(cases)} isolated cases from {isolated_path}")
            async with httpx.AsyncClient() as client:
                results = await run_isolated_cases(client, cases)
            summary = analyze_results(results, "isolated")
            print_summary(summary)
            all_results.extend(results)
            all_summaries.append(summary)
        else:
            print(f"No isolated cases found at {isolated_path}")

    # Scenario mode
    if args.mode in ("scenario", "all", "blind-scenario", "blind-all"):
        if args.mode.startswith("blind"):
            scenario_path = args.blind_scenarios
        else:
            scenario_path = args.scenarios
        if scenario_path.exists():
            scenarios = load_cases(scenario_path)
            print(f"\nLoaded {len(scenarios)} scenarios from {scenario_path}")
            async with httpx.AsyncClient() as client:
                results = await run_scenario_cases(client, scenarios)
            summary = analyze_results(results, "scenario")
            print_summary(summary)
            all_results.extend(results)
            all_summaries.append(summary)
        else:
            print(f"No scenarios found at {scenario_path}")

    # Combined summary for all / blind-all mode
    if args.mode in ("all", "blind-all") and len(all_summaries) == 2:
        total_pass = sum(s["pass_count"] for s in all_summaries)
        total_success = sum(s["success_count"] for s in all_summaries)
        combined_summary = {
            "mode": "all",
            "isolated_summary": all_summaries[0],
            "scenario_summary": all_summaries[1],
            "total_cases": sum(s["total_cases"] for s in all_summaries),
            "pass_count": total_pass,
            "fail_count": sum(s["fail_count"] for s in all_summaries),
            "pass_rate": round(total_pass / total_success, 2) if total_success else 0,
        }
        print("\n" + "=" * 60)
        print("COMBINED SUMMARY")
        print("=" * 60)
        print(f"Total cases: {combined_summary['total_cases']}")
        print(f"PASS: {combined_summary['pass_count']} | FAIL: {combined_summary['fail_count']}")
        print(f"Overall pass rate: {combined_summary['pass_rate']}")
        print("=" * 60)
        # Use combined for threshold check
        check_summary = combined_summary
    else:
        check_summary = all_summaries[0] if all_summaries else {"pass_rate": 0}

    # Save results
    save_results(all_results, check_summary, args.out)

    if check_summary["pass_rate"] < args.threshold:
        print(f"\n❌ PASS RATE {check_summary['pass_rate']} < threshold {args.threshold}")
        return 1
    print(f"\n✅ PASS RATE {check_summary['pass_rate']} >= threshold {args.threshold}")
    return 0


def main() -> None:
    try:
        exit_code = asyncio.run(main_async())
    except KeyboardInterrupt:
        print("\nInterrupted by user")
        exit_code = 130
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
