# Single Turn V1 Baseline

- Date: `2026-06-25`
- Dataset: `benchmarks/memory_routing/data/single_turn_v1.jsonl`
- Evaluator: `benchmarks/memory_routing/scripts/eval_single_turn_routes.py`
- Command: `python3 benchmarks/memory_routing/scripts/eval_single_turn_routes.py --show-failures 0`
- Note: evaluator exits with status `1` when any case fails; this baseline contains failures by design.

## Overall

- `need_memory_accuracy`: `0.650`
- `mention_policy_accuracy`: `0.580`
- `tier_f1`: `0.329`
- `full_route_match`: `0.020`

## By Category

- `adversarial`
  - `total=20`
  - `need_memory_accuracy=0.250`
  - `mention_policy_accuracy=0.250`
  - `tier_f1=0.093`
  - `full_route_match=0.000`

- `background_only`
  - `total=20`
  - `need_memory_accuracy=1.000`
  - `mention_policy_accuracy=1.000`
  - `tier_f1=0.573`
  - `full_route_match=0.100`

- `explicit_recall`
  - `total=20`
  - `need_memory_accuracy=1.000`
  - `mention_policy_accuracy=0.650`
  - `tier_f1=0.477`
  - `full_route_match=0.000`

- `no_memory`
  - `total=20`
  - `need_memory_accuracy=0.000`
  - `mention_policy_accuracy=0.000`
  - `tier_f1=0.000`
  - `full_route_match=0.000`

- `personalized_advice`
  - `total=20`
  - `need_memory_accuracy=1.000`
  - `mention_policy_accuracy=1.000`
  - `tier_f1=0.500`
  - `full_route_match=0.000`

## Quick Read

- The current system strongly over-retrieves memory for `no_memory` cases.
- `adversarial` cases are also weak, which suggests trigger words easily cause false-positive memory routing.
- `background_only` and `personalized_advice` are directionally better on `need_memory`, but tier selection is still too broad.
