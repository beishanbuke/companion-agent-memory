from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import types
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]

import sys

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _install_openai_stub() -> None:
    if "openai" in sys.modules:
        return

    class _AsyncOpenAI:
        def __init__(self, *args, **kwargs):
            self.chat = types.SimpleNamespace(completions=types.SimpleNamespace(create=None))

    sys.modules["openai"] = types.SimpleNamespace(AsyncOpenAI=_AsyncOpenAI)


def _load_situation_router_module():
    _install_openai_stub()
    module_path = PROJECT_ROOT / "companion_agent" / "situation_router.py"
    spec = importlib.util.spec_from_file_location("benchmark_situation_router", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load situation_router from {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_situation_router_module = _load_situation_router_module()
RoutingDecision = _situation_router_module.RoutingDecision
SituationRouter = _situation_router_module.SituationRouter


def _load_memory_router_module():
    module_path = PROJECT_ROOT / "companion_agent" / "memory_router.py"
    spec = importlib.util.spec_from_file_location("benchmark_memory_router", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load memory_router from {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_memory_router_module = _load_memory_router_module()
MemoryRouter = _memory_router_module.MemoryRouter


@dataclass
class PredictedRoute:
    situation: str
    confidence: float
    need_memory: bool
    tiers: list[str]
    mention_policy: str


def _normalize_tiers(tiers: list[str]) -> list[str]:
    normalized = []
    for tier in tiers:
        value = str(tier).strip()
        if value and value not in normalized:
            normalized.append(value)
    return normalized


def _mention_policy_from_routing(decision: RoutingDecision) -> str:
    if decision.situation == "memory_query":
        return "explicit_ok"
    if decision.retrieve_memory:
        return "implicit_only"
    return "forbid"


class CurrentSystemRoutePredictor:
    """Offline route predictor based on the current in-repo SituationRouter.

    This intentionally disables the LLM classifier so benchmark runs stay
    deterministic and cheap.
    """

    def __init__(self, fixed_situation: str | None = None):
        self._router = SituationRouter()
        self._router._client = None
        self._memory_router = MemoryRouter()
        self._fixed_situation = fixed_situation

    async def predict(
        self,
        *,
        user_message: str,
        history: list[dict[str, str]] | None = None,
        memory_snapshot: dict[str, Any] | None = None,
    ) -> PredictedRoute:
        if self._fixed_situation:
            decision = self._router._build_decision(self._fixed_situation, 1.0)
        else:
            decision = await self._router.classify(user_message, history or [])
        memory_route = self._memory_router.route(
            user_message=user_message,
            conversation_history=history or [],
            situation=decision.situation,
            situation_confidence=decision.confidence,
            current_memory_snapshot=memory_snapshot,
        )
        return PredictedRoute(
            situation=decision.situation,
            confidence=decision.confidence,
            need_memory=memory_route.need_memory,
            tiers=_normalize_tiers(memory_route.tiers),
            mention_policy=memory_route.mention_policy,
        )


def load_cases(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rows.append(json.loads(line))
    return rows


def jaccard_f1(expected: list[str], predicted: list[str]) -> float:
    expected_set = set(expected)
    predicted_set = set(predicted)
    if not expected_set and not predicted_set:
        return 1.0
    if not expected_set or not predicted_set:
        return 0.0
    intersection = len(expected_set & predicted_set)
    precision = intersection / len(predicted_set)
    recall = intersection / len(expected_set)
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


async def evaluate_dataset(
    *,
    dataset_path: Path,
    show_failures: int,
    fixed_situation: str | None,
) -> int:
    predictor = CurrentSystemRoutePredictor(fixed_situation=fixed_situation)
    cases = load_cases(dataset_path)

    total = len(cases)
    need_memory_correct = 0
    mention_policy_correct = 0
    full_match_correct = 0
    tier_f1_total = 0.0
    category_stats: dict[str, Counter] = defaultdict(Counter)
    failures: list[dict[str, Any]] = []

    for case in cases:
        expected_route = case["expected_route"]
        predicted = await predictor.predict(
            user_message=case["user_message"],
            history=case.get("history") or [],
            memory_snapshot=case.get("memory_snapshot"),
        )

        expected_need_memory = bool(expected_route["need_memory"])
        expected_tiers = _normalize_tiers(expected_route["tiers"])
        expected_mention_policy = str(expected_route["mention_policy"])

        need_memory_ok = predicted.need_memory == expected_need_memory
        tiers_ok = set(predicted.tiers) == set(expected_tiers)
        mention_policy_ok = predicted.mention_policy == expected_mention_policy
        full_match_ok = need_memory_ok and tiers_ok and mention_policy_ok
        tier_f1 = jaccard_f1(expected_tiers, predicted.tiers)

        category = str(case["category"])
        category_stats[category]["total"] += 1
        category_stats[category]["need_memory_correct"] += int(need_memory_ok)
        category_stats[category]["mention_policy_correct"] += int(mention_policy_ok)
        category_stats[category]["full_match_correct"] += int(full_match_ok)
        category_stats[category]["tier_f1_points"] += int(round(tier_f1 * 1000))

        need_memory_correct += int(need_memory_ok)
        mention_policy_correct += int(mention_policy_ok)
        full_match_correct += int(full_match_ok)
        tier_f1_total += tier_f1

        if not full_match_ok:
            failures.append(
                {
                    "id": case["id"],
                    "category": category,
                    "user_message": case["user_message"],
                    "expected_route": expected_route,
                    "predicted_route": {
                        "situation": predicted.situation,
                        "confidence": round(predicted.confidence, 3),
                        "need_memory": predicted.need_memory,
                        "tiers": predicted.tiers,
                        "mention_policy": predicted.mention_policy,
                    },
                    "notes": case.get("notes", ""),
                }
            )

    print(f"Dataset: {dataset_path}")
    print(f"Cases: {total}")
    print(f"Mode: {'isolated (' + fixed_situation + ')' if fixed_situation else 'pipeline'}")
    print()
    print("Overall")
    print(f"- need_memory_accuracy: {need_memory_correct / total:.3f}")
    print(f"- mention_policy_accuracy: {mention_policy_correct / total:.3f}")
    print(f"- tier_f1: {tier_f1_total / total:.3f}")
    print(f"- full_route_match: {full_match_correct / total:.3f}")
    print()
    print("By Category")

    for category in sorted(category_stats):
        stats = category_stats[category]
        category_total = stats["total"]
        tier_f1_avg = (stats["tier_f1_points"] / 1000.0) / category_total
        print(f"- {category}")
        print(f"  total={category_total}")
        print(f"  need_memory_accuracy={stats['need_memory_correct'] / category_total:.3f}")
        print(f"  mention_policy_accuracy={stats['mention_policy_correct'] / category_total:.3f}")
        print(f"  tier_f1={tier_f1_avg:.3f}")
        print(f"  full_route_match={stats['full_match_correct'] / category_total:.3f}")

    if show_failures > 0:
        print()
        print(f"Sample Failures ({min(show_failures, len(failures))}/{len(failures)})")
        for failure in failures[:show_failures]:
            print(json.dumps(failure, ensure_ascii=False, indent=2))

    return 1 if failures else 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate single-turn memory routing benchmark without API calls."
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=PROJECT_ROOT / "benchmarks" / "memory_routing" / "data" / "single_turn_v1.jsonl",
        help="Path to the benchmark JSONL dataset.",
    )
    parser.add_argument(
        "--show-failures",
        type=int,
        default=10,
        help="Number of failed cases to print.",
    )
    parser.add_argument(
        "--fixed-situation",
        choices=sorted(SituationRouter.SITUATIONS),
        help="Bypass SituationRouter and evaluate MemoryRouter with one fixed situation.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    return asyncio.run(
        evaluate_dataset(
            dataset_path=args.dataset,
            show_failures=args.show_failures,
            fixed_situation=args.fixed_situation,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
