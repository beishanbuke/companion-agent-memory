#!/usr/bin/env python3
"""Rule/LLM emotion-detector eval over benchmarks/emotion_lite/eval_cases.json.

Usage:
    python benchmarks/emotion_lite/run_eval.py             # rule detector only
    python benchmarks/emotion_lite/run_eval.py --llm       # also run the LLM judge

Rule accuracy is gated over non-hard cases (hard cases need the LLM judge:
sarcasm, denial, mixed emotions). Exit code is non-zero when the gate fails,
so this script can run in CI.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BENCHMARK_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BENCHMARK_DIR.parent.parent
sys.path.insert(0, str(PROJECT_DIR))

from companion_agent.emotion_detector import CurrentEmotionDetector  # noqa: E402

RULE_GATE = 0.8


def load_cases() -> list[dict]:
    return json.loads((BENCHMARK_DIR / "eval_cases.json").read_text(encoding="utf-8"))


def rule_result(detector: CurrentEmotionDetector, case: dict) -> dict:
    r = detector.detect_by_rule(case["message"])
    return {
        "label": r.label,
        "secondary_label": r.secondary_label,
        "intensity": r.intensity,
    }


def llm_result(detector: CurrentEmotionDetector, case: dict) -> dict:
    r = detector.detect(case["message"])
    return {
        "label": r.label,
        "secondary_label": r.secondary_label,
        "intensity": r.intensity,
        "confidence": r.confidence,
        "llm": "llm_judge" in r.signals and "llm_judge_failed" not in r.signals,
    }


def score(cases: list[dict], results: list[dict], eligible: list[dict]) -> dict:
    ok = sum(1 for c, r in zip(eligible, results) if r["label"] == c["expect"])
    return {"n": len(eligible), "correct": ok, "accuracy": round(ok / len(eligible), 3) if eligible else 0.0}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--llm", action="store_true", help="also run the LLM judge (needs API env keys)")
    args = parser.parse_args()

    cases = load_cases()
    detector = CurrentEmotionDetector()
    rule_eligible = [c for c in cases if not c.get("hard")]

    rule_results = [rule_result(detector, c) for c in rule_eligible]
    rule_score = score(cases, rule_results, rule_eligible)

    print("== rule detector (non-hard cases) ==")
    for c, r in zip(rule_eligible, rule_results):
        mark = "✓" if r["label"] == c["expect"] else "✗"
        print(f"  {mark} [{c['id']}] expect={c['expect']} got={r['label']} sec={r['secondary_label']}")
    print(f"  accuracy: {rule_score['correct']}/{rule_score['n']} = {rule_score['accuracy']}")

    exit_code = 0
    if rule_score["accuracy"] < RULE_GATE:
        print(f"RULE GATE FAILED (< {RULE_GATE})")
        exit_code = 1

    if args.llm:
        llm_results = [llm_result(detector, c) for c in cases]
        ok = sum(1 for c, r in zip(cases, llm_results) if r["label"] == c["expect"])
        sec_ok = sum(
            1 for c, r in zip(cases, llm_results)
            if not c.get("secondary_expect") or r["secondary_label"] == c["secondary_expect"]
        )
        llm_ok = sum(1 for r in llm_results if r["llm"])
        print("\n== llm judge (all cases) ==")
        for c, r in zip(cases, llm_results):
            mark = "✓" if r["label"] == c["expect"] else "✗"
            print(
                f"  {mark} [{c['id']}] expect={c['expect']} got={r['label']}"
                f" sec={r['secondary_label']} conf={r.get('confidence')}"
            )
        print(f"  llm reachable: {llm_ok}/{len(cases)}")
        print(f"  accuracy: {ok}/{len(cases)} = {round(ok / len(cases), 3)}")
        print(f"  secondary accuracy: {sec_ok}/{len(cases)}")

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
