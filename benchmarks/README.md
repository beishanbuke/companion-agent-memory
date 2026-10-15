# Benchmarks

This directory stores offline evaluation datasets, benchmark specs, scoring notes,
and result snapshots for the project.

Suggested layout:

- `memory_routing/`: benchmarks for memory retrieval routing and over-memory behavior
- `*/data/`: source benchmark cases and generated datasets
- `*/scripts/`: generation and scoring scripts
- `*/reports/`: saved evaluation outputs

Keep benchmark assets separate from `tests/`:

- `tests/` checks code correctness
- `benchmarks/` measures behavior quality
