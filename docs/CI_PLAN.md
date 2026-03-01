# CI / Coverage / Benchmark Plan

## CI (Linux x86-64)

Minimum CI gates:
- `python -m pytest -q`

Optional gates (later):
- formatting / lint (keep optional until style is stabilized)
- a small curated conformance run

## Coverage

- Generate coverage reports periodically (not necessarily gating at first).
- Track coverage trend to avoid silent regression.

Suggested commands (local):
- `python -m pip install -r requirements.txt`
- `python -m pytest -q`
- `python -m pytest --cov=pycc --cov-report=term-missing`

## Benchmarks (minimal)

Track two metrics over time:
- compile time on a small corpus (e.g., `examples/*.c`)
- run time sanity (already covered by many integration tests)

Do not gate on benchmarks initially; record baselines to detect big regressions.
