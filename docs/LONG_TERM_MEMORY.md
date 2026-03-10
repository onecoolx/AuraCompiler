# Long-Term Memory (Project + Workflow)

Last updated: 2026-03-10

This document captures durable project context so work can continue smoothly even if conversation context is lost or a different agent takes over.

## 1) Project goal and scope

**AuraCompiler (pycc)** is a practical C89/ANSI C compiler written in Python targeting **x86-64 SysV Linux**.

### Goals

- Compile a useful subset of C89 end-to-end: **Lexer → Parser → Semantics → IR → Codegen → system toolchain (as/ld or gcc link)**.
- Stay **test-driven** with a fast, reliable `pytest` suite.

### Non-goals (for now)

- Full C89 conformance, floating point (`float`/`double`), complete preprocessor, and a full multi-translation-unit/linker model.

## 2) Architecture (stable invariants)

### Pipeline

- `pycc/lexer.py`: tokenize
- `pycc/parser.py`: build AST (`pycc/ast_nodes.py`)
- `pycc/semantics.py`: name resolution, type-ish checks (best-effort, conservative where needed)
- `pycc/ir.py`: lower AST to minimal TAC-like IR (`IRInstruction`)
- `pycc/optimizer.py`: optional passes
- `pycc/codegen.py`: x86-64 SysV assembly
- `pycc/compiler.py`: orchestration + toolchain integration

### Backend ABI invariants (must not regress)

- **SysV AMD64 stack alignment**: `%rsp` must be **16-byte aligned at each `call`**.
- **Varargs calls**: when calling variadic functions (e.g. `printf`), set `%al` to the number of vector registers used (currently **0**).

### Stack frame layout invariant (must not regress)

Within a function, stack slots must never overlap:

1. **Declared locals**: assigned fixed `rbp`-relative slots first.
2. **Temp spill region**: a reserved region used for IR temporaries `%t*`.
3. **Late-discovered locals**: if codegen must allocate a new local slot after the prologue scan, it must be placed **below** the spill region.

Reason: IR comparisons and other expressions store results into `%t*` temps; if temps overlap user locals (e.g. `@i`), program state can be corrupted (e.g. for-loop infinite loops).

## 3) Current progress snapshot (update when changes land)

- End-to-end compilation works for a practical C89-ish subset.
- Test suite is the source of truth.

Single source of truth for human-readable status:
- `docs/C89_ROADMAP.md` (language roadmap)
- `docs/PREPROCESSOR_C89_CHECKLIST.md` (quantified preprocessor gap)
- `docs/C89_CONFORMANCE_MATRIX.md` (spec area ↔ tests ↔ status; if present)

When updating this snapshot, include:
- `pytest -q` result summary (counts)
- any newly supported feature and the test file proving it
- any important known gaps/regressions

Current snapshot (2026-03-10):

- Tests: `pytest -q` → **597 passed**
- Multi-TU model (practical subset):
  - tentative globals emitted as `.comm`
  - `extern` declarations do not allocate storage in a TU
  - cross-TU conflicts checked in driver tests
- Multi-dimensional arrays (2D) incremental support:
  - Parser records `Declaration.array_dims` (outer→inner), keeping backward compat with `array_size`.
  - 2D array decay to pointer-to-row via IR `meta["ptr_step_bytes"]` and codegen scaling.
  - `sizeof(local 2D array)` returns total bytes (dims product * element size).
  - Nested indexing `a[i][j]` is **not correct yet**; guarded by:
    - `tests/test_multi_dim_array_init_and_index.py` (now passes)

## 4) Engineering workflow rules (fast iteration)

Project rule of thumb: keep iteration fast while preserving correctness.

### 4.1 Per-commit test policy

- **Normal iterations (most commits): run impacted unit tests only.**
  - Use: `python scripts/run_impact_tests.py --since HEAD`
  - Rationale: avoid running the full suite on every small change.
  - This script maps changed file paths to relevant pytest test globs and runs
    the union.

- **Milestones / larger phases: run the full test suite once.**
  - Use: `python scripts/run_impact_tests.py --all` (equivalent to `pytest -q`)
  - If full-suite regressions occur: fix them first, restore green, then commit
    following the same workflow.

- **只要完成一次测试执行（无论是 impacted 还是 full suite），并且结果全绿通过，就必须提交一次代码。**
  - 使用：`../ap.sh "<commitlint msg>"`
  - 目的：确保“绿测试”与“可回溯提交”一一对应，避免出现通过测试但未落盘的状态。

### 4.2 Suggested loop

1) Make a small, scoped change.
2) Run impacted tests:
   - `python scripts/run_impact_tests.py --since HEAD`
3) Commit.
4) At milestone boundaries: run full suite once:
   - `python scripts/run_impact_tests.py --all`

Notes:
- For docs-only changes, impacted tests may be empty; this is OK.
- Prefer multiple small commits over one large commit.

## 4) Engineering workflow (implementation rules)

### Tests-first and quality gates

- Write/extend a failing test first when adding or fixing behavior.
- Fast iteration policy:
  - For most commits, run **only impacted tests** for the changed modules.
  - For **docs-only** updates (`README.md`, `docs/**`), **skip tests**.
  - At a **milestone** (or before publishing), run the **full suite**: `pytest -q`.
- Prefer small, reviewable steps.

Impacted test selection is path-based and automated by:

```
python scripts/run_impact_tests.py
```

### Where to fix a bug (preferred order)

1. `pycc/semantics.py` (analysis / typing / validation)
2. `pycc/ir.py` (lowering)
3. `pycc/codegen.py` (emission)

### Code style and comments

- Remove debug-only comments and incidental narrative from code.
- Keep comments for:
  - ABI/algorithm invariants
  - non-obvious reasoning
  - tricky edge cases proved by tests

## 5) Commit and documentation rules

### Commit rule (mandatory)

- Commits must use a **commitlint-style** message in English, e.g.
  - `fix(codegen): prevent local/temp stack slot aliasing`
  - `test(codegen): add regression for spill stack growth`
- Commits must be created via the helper script:

```
../ap.sh "<commit message>"
```

Practical convention used in this repo (examples):

- `fix(array): ...`
- `feat(array): ...`
- `test(stdarg): ...`
- `docs: ...`

This ensures author metadata is attached consistently.

### Documentation update rule

Whenever behavior/status changes:

- Update `docs/PROJECT_SUMMARY.md`:
  - test counts
  - implemented highlights / known gaps
  - brief description of important fixes and why they matter
- If a change establishes a new invariant or workflow rule, also update this file (`docs/LONG_TERM_MEMORY.md`).
