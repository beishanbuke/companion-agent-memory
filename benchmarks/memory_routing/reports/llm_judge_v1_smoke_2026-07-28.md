# LLM Judge v1 Smoke Benchmark

Date: 2026-07-28

Dataset:

```text
benchmarks/memory_routing/data/llm_judge_v1_smoke.jsonl
```

Command:

```bash
./condaenv/bin/python benchmarks/memory_routing/scripts/eval_single_turn_routes.py \
  --dataset benchmarks/memory_routing/data/llm_judge_v1_smoke.jsonl \
  --show-failures 12
```

Result:

```text
Cases: 12
need_memory_accuracy: 1.000
mention_policy_accuracy: 1.000
tier_f1: 1.000
full_route_match: 1.000
```

Covered categories:

- explicit profile recall
- background beverage preference
- explicit preference history
- background support style
- explicit memory disable
- short-term context request
- generic knowledge task
- third-party recommendation
- goal planning
- recent event planning
- safety-sensitive memory routing
- default no-memory route

Notes:

- The smoke set is designed for fast regression checks, not broad statistical claims.
- `llm_judge_v1` keeps rule guardrails for high-precision cases and falls back to `rule_based_v2` when the LLM judge is unavailable or invalid.
