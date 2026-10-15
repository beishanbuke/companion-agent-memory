"""Regression gate: rule detector accuracy over benchmarks/emotion_lite.

Hard cases (sarcasm, denial, mixed emotions) are excluded — they require
the LLM judge and are scored by benchmarks/emotion_lite/run_eval.py --llm.
"""

import json
from pathlib import Path

from companion_agent.emotion_detector import CurrentEmotionDetector

BENCHMARK_DIR = Path(__file__).resolve().parent.parent / "benchmarks" / "emotion_lite"
RULE_GATE = 0.8


def _cases() -> list[dict]:
    return json.loads((BENCHMARK_DIR / "eval_cases.json").read_text(encoding="utf-8"))


def test_rule_accuracy_on_benchmark() -> None:
    detector = CurrentEmotionDetector()
    eligible = [c for c in _cases() if not c.get("hard")]
    correct = sum(
        1 for c in eligible
        if detector.detect_by_rule(c["message"]).label == c["expect"]
    )
    accuracy = correct / len(eligible)
    assert accuracy >= RULE_GATE, (
        f"rule accuracy {correct}/{len(eligible)} = {accuracy:.2f} < {RULE_GATE}"
    )
