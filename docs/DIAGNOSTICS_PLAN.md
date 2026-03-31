# Diagnostics Plan

Goal: consistent, testable diagnostics across the compiler.

## Output format

All diagnostics should follow a uniform format:

- **error**:
  - `error: <message> (at <file>:<line>:<col>)`
- **warning**:
  - `warning: <message> (at <file>:<line>:<col>)`

Where location is best-effort:
- prefer token/AST locations when available
- otherwise fall back to `?:?:?`

## Severity policy

- Errors: compilation fails, non-zero exit.
- Warnings: compilation succeeds; warnings collected and optionally printed.

## Optional error codes (future)

If/when added, format becomes:
- `error[E0123]: <message> (at <file>:<line>:<col>)`

This enables stable tests without depending on exact wording.

## Implementation plan (phased)

1) Standardize internal error collection APIs (compiler result objects)
2) Ensure preprocessor errors include file/line where possible
3) Ensure parser/semantics errors include token locations
4) Add tests asserting:
   - correct severity
   - location present
   - code present (if enabled)

## Current state (2026-03-31)

- Compiler driver (`pycc/compiler.py`) formats errors uniformly and attaches `(at <file>:<line>:<col>)`.
- Semantic analysis now records best-effort locations by appending ` at <line>:<col>` to specific error messages when an AST node has `line/column`. The driver extracts this suffix and uses it for stable location formatting.
- Tests cover semantics-location formatting for representative errors:
  - `tests/test_diagnostics_semantics_location_for_sizeof.py`
  - `tests/test_diagnostics_semantics_location_for_cast.py`
