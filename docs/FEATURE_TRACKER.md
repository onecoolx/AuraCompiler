# AuraCompiler Feature Tracker (Living)

Last updated: 2026-02-25

This is the **single source of truth** for feature status.

Legend:
- **DONE**: implemented + tests merged and passing
- **PARTIAL**: subset implemented + tests passing
- **TODO**: not implemented

Rule: every new feature must add/extend tests under `tests/`.

---

## Milestone 1 — C89 Language Core (do not disable C99 extensions)

### Declarations / Types

- **DONE** typedef — `tests/test_typedef.py`
- **DONE** struct/union layout + member access — `tests/test_struct_union.py`, `tests/test_member_access.py`, `tests/test_member_semantics.py`
- **DONE** enum constants (incl. auto increment) — `tests/test_enum.py`
- **PARTIAL** storage class (`static`/`extern`) — `tests/test_storage_class.py`
- **PARTIAL** full declarator grammar (function pointers etc.) — TODO
- **PARTIAL** function pointer local declarations + indirect calls (subset) — `tests/test_declarators.py`
- **PARTIAL** array of function pointers declarator (subset) — `tests/test_declarators.py`
- **PARTIAL** function pointer parameters (subset) — `tests/test_declarators.py`
- **PARTIAL** functions returning function pointers (subset; incl. prototype/extern) — `tests/test_declarators.py`

### Expressions / Operators

- **DONE** arithmetic/bitwise/compare/assignment/calls/?: — covered across many tests
- **DONE** `sizeof` (subset) — `tests/test_sizeof.py`
- **DONE** C-style cast (subset) — `tests/test_cast.py`
- **DONE** `&&`/`||` short-circuit — `tests/test_short_circuit.py`
- **PARTIAL** conditional operator (`?:`) usual arithmetic conversions (unsigned int/unsigned long cases) — `tests/test_int_conversions.py`
- **PARTIAL** integer promotions + usual arithmetic conversions — comparisons for `int` vs `unsigned int` (best-effort) — `tests/test_int_conversions.py`
- **PARTIAL** usual arithmetic conversions involving `unsigned long` (tests) — `tests/test_int_conversions.py`
- **PARTIAL** unsigned `unsigned long` division/modulo semantics (tests) — `tests/test_int_conversions.py`
- **PARTIAL** unsigned 32-bit arithmetic wrap for `+/-/*` (best-effort) — `tests/test_int_conversions.py`
- **PARTIAL** unsigned 32-bit division/modulo for `/` and `%` (best-effort) — `tests/test_int_conversions.py`
- **PARTIAL** shift semantics: unsigned `>>` logical, signed `>>` arithmetic (best-effort) — `tests/test_int_conversions.py`
- **PARTIAL** compound assignment conversions for `unsigned int` (best-effort) — `tests/test_int_conversions.py`
- **PARTIAL** integer promotions for `short`/`unsigned short` (tests) — `tests/test_int_conversions.py`
- **PARTIAL** comparisons involving `short`/`unsigned short` after promotions (tests) — `tests/test_int_conversions.py`
- **PARTIAL** assignment narrowing/truncation for `char`/`short` (tests) — `tests/test_int_conversions.py`
- **PARTIAL** load sign/zero extension for `char`/`short` (tests) — `tests/test_int_conversions.py`
- **PARTIAL** compound assignment truncation for `char`/`short` (tests) — `tests/test_int_conversions.py`
- **PARTIAL** pointer arithmetic completeness — `tests/test_pointer_arith.py` (more TODO)

### Statements / Control Flow

- **DONE** if/while/do/for — integration tests
- **DONE** switch/case/default — `tests/test_switch.py`
- **DONE** break/continue — integration tests
- **DONE** goto/labels — `tests/test_goto.py`

### Initialization / Data

- **PARTIAL** global string literal pointer init — `tests/test_global_string_ptr.py`
- **PARTIAL** local array initializers (non-designated): `int a[N] = {..}` and zero-fill, plus `char s[] = "..."` — `tests/test_initializer_aggregate.py`
- **TODO** struct initializers (`struct S x = { ... }`) and nested aggregate init
- **TODO** global aggregate initializers (emit `.data` bytes/relocations)

---

## Milestone 2 — Preprocessor + Multi-file + glibc

- **TODO** Preprocessor stage (`-E`): includes, macros, conditional compilation, line control
- **TODO** Driver supports multiple inputs: `pycc file1.c file2.c -o a.out`
- **TODO** Emit `.o` and link with system glibc reliably
- Tests:
  - `tests/test_preprocessor_*.py`
  - `tests/test_multifile_linking.py`

---

## Milestone 3 — Strict C89 coverage

- **TODO** tighten semantics & diagnostics (compatible redecls, incomplete types, qualifier rules, etc.)
- **TODO** conformance corpus and gcc comparison runs

---

## Milestone 4 — gcc/clang-compatible driver

- **TODO** CLI parity (subset): `-c`, `-S`, `-E`, `-o`, `-I`, `-D`, `-U`, `-std=`, `-Wall/-Werror`, `-O0/-O1`

---

## Milestone 5 — Diagnostics

- **TODO** consistent English diagnostics (source ranges, notes, carets)
- **TODO** error codes/categories, and test expectations for error messages
