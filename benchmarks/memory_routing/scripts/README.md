# Scripts

Planned scripts:

- dataset generation
- route evaluation
- response scoring
- report aggregation

Current script:

- `eval_single_turn_routes.py`
  - Runs the current `SituationRouter` offline
  - Disables LLM routing for deterministic evaluation
  - Compares `need_memory`, `tiers`, and `mention_policy`
