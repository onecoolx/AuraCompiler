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
