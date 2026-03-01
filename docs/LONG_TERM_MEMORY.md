# Long-Term Memory (Project + Workflow)

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

When updating this snapshot, include:
- `pytest -q` result summary (counts)
- any newly supported feature and the test file proving it
- any important known gaps/regressions

## 4) Engineering workflow (implementation rules)

### Tests-first and quality gates

- Write/extend a failing test first when adding or fixing behavior.
- **All changes must pass** `pytest -q` **before any commit**.
- Prefer small, reviewable steps.

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

This ensures author metadata is attached consistently.

### Documentation update rule

Whenever behavior/status changes:

- Update `docs/PROJECT_SUMMARY.md`:
  - test counts
  - implemented highlights / known gaps
  - brief description of important fixes and why they matter
- If a change establishes a new invariant or workflow rule, also update this file (`docs/LONG_TERM_MEMORY.md`).
