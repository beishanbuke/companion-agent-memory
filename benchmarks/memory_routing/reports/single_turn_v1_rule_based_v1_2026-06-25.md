# Single Turn V1 - Rule Based Memory Router V1

- Date: `2026-06-25`
- Dataset: `benchmarks/memory_routing/data/single_turn_v1.jsonl`
- Evaluator: `benchmarks/memory_routing/scripts/eval_single_turn_routes.py`
- Router version: `rule_based_v1`
- Command: `python3 benchmarks/memory_routing/scripts/eval_single_turn_routes.py --show-failures 5`

## Overall

- `need_memory_accuracy`: `0.900`
- `mention_policy_accuracy`: `0.900`
- `tier_f1`: `0.774`
- `full_route_match`: `0.640`

## By Category

- `adversarial`
  - `total=20`
  - `need_memory_accuracy=0.850`
  - `mention_policy_accuracy=0.850`
  - `tier_f1=0.833`
  - `full_route_match=0.800`

- `background_only`
  - `total=20`
  - `need_memory_accuracy=0.850`
  - `mention_policy_accuracy=0.850`
  - `tier_f1=0.617`
  - `full_route_match=0.350`

- `explicit_recall`
  - `total=20`
  - `need_memory_accuracy=0.850`
  - `mention_policy_accuracy=0.850`
  - `tier_f1=0.817`
  - `full_route_match=0.750`

- `no_memory`
  - `total=20`
  - `need_memory_accuracy=0.950`
  - `mention_policy_accuracy=0.950`
  - `tier_f1=0.950`
  - `full_route_match=0.950`

- `personalized_advice`
  - `total=20`
  - `need_memory_accuracy=1.000`
  - `mention_policy_accuracy=1.000`
  - `tier_f1=0.655`
  - `full_route_match=0.350`

## Delta vs Baseline

- `need_memory_accuracy`: `0.650 -> 0.900`
- `mention_policy_accuracy`: `0.580 -> 0.900`
- `tier_f1`: `0.329 -> 0.774`
- `full_route_match`: `0.020 -> 0.640`

## Quick Read

- `no_memory` improved sharply, which directly targets the over-memory issue.
- `adversarial` also improved a lot, which suggests false-positive memory triggers are reduced.
- The main remaining gap is finer tier selection for `background_only` and `personalized_advice`.
