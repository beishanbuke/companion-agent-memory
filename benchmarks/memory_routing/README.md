# Memory Routing Benchmark

This benchmark targets one concrete problem: the model overuses old memories in
responses, even when the current user turn does not need memory grounding.

Primary goals:

1. Measure whether memory should be retrieved at all.
2. Measure which memory tiers should be retrieved.
3. Measure whether the final answer should explicitly mention past memory.
4. Measure whether the final answer over-cues irrelevant memory.

Recommended benchmark phases:

1. Routing-only benchmark
2. Full generation benchmark
3. Judge/scoring benchmark

Files:

- `data/benchmark.schema.json`: per-sample schema
- `data/synthetic_v1.example.jsonl`: example cases
- `data/single_turn_v1.jsonl`: 100-case single-turn benchmark
- `data/llm_judge_v1_smoke.jsonl`: 12-case smoke set for hybrid LLM judge routing
- `scripts/`: future generation and scoring tools
- `reports/`: saved benchmark outputs

Run the full routing pipeline:

```bash
python3 benchmarks/memory_routing/scripts/eval_single_turn_routes.py
```

To isolate MemoryRouter from SituationRouter, supply a fixed situation:

```bash
python3 benchmarks/memory_routing/scripts/eval_single_turn_routes.py \
  --fixed-situation casual_chat
```

Run the LLM judge smoke set:

```bash
MEMORY_ROUTER_VERSION=llm_judge_v1 \
python3 benchmarks/memory_routing/scripts/eval_single_turn_routes.py \
  --dataset benchmarks/memory_routing/data/llm_judge_v1_smoke.jsonl \
  --show-failures 12
```

If the judge API is unavailable, `llm_judge_v1` falls back to `rule_based_v2`
and marks the route with `llm_judge_failed` in its signals.
