# C89 Preprocessor Checklist (Quantified)

Last updated: 2026-02-27

Purpose:
- Provide a **quantified gap** vs. a "full" C89-style preprocessor.
- Provide a **prioritized checklist** for continued development.
- Keep this document stable and actionable: each item should map to tests + code changes.

Legend:
- [x] DONE: implemented + tests in tree
- [~] PARTIAL: subset implemented + tests in tree
- [ ] TODO: not implemented

Notes:
- AuraCompiler currently supports both an **internal** preprocessor (`pycc.py -E`) and an option to use **system cpp** (`--use-system-cpp`). This checklist focuses on the **internal** preprocessor correctness/coverage.
- Some items are technically beyond strict C89 but are common in real-world headers (called out explicitly).

---

## 0) Quantified summary

Counts below are *checklist-item counts* (not lines of code).

- Core directive parsing + inactive-region rules: **[x] 9 / 9**
- Includes + include search: **[~] 8 / 12**
- Macro definitions (object/function) + expansion engine: **[~] 12 / 26**
- Operators `#` / `##`: **[~] 5 / 10**
- Conditional expressions (`#if` / `#elif`): **[~] 12 / 18**
- Predefined macros (C89 set): **[~] 4 / 6**
- Line control / diagnostics behavior: **[~] 2 / 6**

Overall (this doc): **DONE 15 + PARTIAL 31 + TODO 40 = 86 items**

Interpretation:
- The project has a *broad* subset already, including many `#if` operators and several macro operators.
- The largest remaining gap is the **standards-accurate macro expansion algorithm** (tokenization + hide-sets + rescanning semantics).

---

## 1) Directive parsing / structure (priority: P0)

These are required to safely process real-world code without crashing or mis-nesting.

- [x] Recognize directives with leading whitespace (`\s*#\s*...`) — `tests/test_preprocessor_directive_whitespace.py`
- [x] Handle nested conditionals structurally (stack-based) — `tests/test_preprocessor_nested_conditionals.py`
- [x] `#if 0` / `#if 1` / `#else` / `#endif` basic flow — `tests/test_preprocessor_if0.py`, `tests/test_preprocessor_else.py`
- [x] `#ifdef` / `#ifndef` — `tests/test_preprocessor_ifdef.py`, `tests/test_preprocessor_ifndef.py`
- [x] `#elif 0/1` + `#elif NAME` (legacy strict 0/1) — `tests/test_preprocessor_elif.py`
- [x] `#elifdef` / `#elifndef` — `tests/test_preprocessor_elifdef_elifndef.py`
- [x] **Inactive-region rule**: do not parse/evaluate malformed `#if` expressions when parent is inactive — `tests/test_preprocessor_defined_inactive_branch_no_error.py`
- [x] **Inactive-region rule**: `#define` inside inactive has no effect — `tests/test_preprocessor_define_ignored_in_inactive.py`
- [x] **Inactive-region rule**: `#error`/`#warning`/malformed `#line` ignored inside inactive — `tests/test_preprocessor_error_ignored_in_inactive.py`, `tests/test_preprocessor_warning_ignored_in_inactive.py`, `tests/test_preprocessor_line_directive_ignored_in_inactive.py`

---

## 2) Includes / multi-file (priority: P0/P1)

### Implemented (subset)
- [~] `#include "file"` relative resolution + cycle detection — `tests/test_preprocessor_include.py`
- [~] `#include <...>` via `-I` and best-effort system probing — `tests/test_preprocessor_include_angle.py`, `tests/test_preprocessor_gcc_include_probe.py`
- [x] Reject `#include_next` with explicit error — `tests/test_preprocessor_include_next.py`
- [~] `#pragma once` include-once semantics (subset) + path equivalence edges — `tests/test_preprocessor_pragma_once*.py`

### TODO (gap)
- [ ] Macro-expanded include operands: `#include HEADER` / `#include STR(x)` (standard behavior)
- [ ] Full include search order parity for `""` vs `<>` (standard behavior)
- [ ] `#include` with comments/line splices in header-name tokens (token-level correctness)
- [ ] Proper handling of missing includes: diagnostic quality + include stack reporting
- [ ] `#line` affects include location / builtins consistently
- [ ] `#pragma` generic handling (unknown pragmas ignored with optional diagnostic)

---

## 3) Macro definitions (priority: P0/P1)

### Object-like
- [~] `#define NAME replacement` — `tests/test_preprocessor_define.py`
- [~] `#undef NAME` removes macro — `tests/test_preprocessor_undef.py`
- [~] Chained rescanning to a fixed point (bounded) — `tests/test_preprocessor_macro_rescan.py`
- [~] Cycle safety (bounded; must terminate) — `tests/test_preprocessor_macro_cycle.py`
- [~] Hide-set-like determinism for self-referential replacement (subset) — `tests/test_preprocessor_macro_hideset_determinism.py`
- [~] No expansion inside string/char literals; identifier-only substitution — `tests/test_preprocessor_macro_expansion_edges.py`

### Function-like
- [~] `#define F(x) ...` + invoke `F(1)` — `tests/test_preprocessor_function_like_macros.py`
- [~] Nested calls (best-effort) — `tests/test_preprocessor_function_like_macros.py`
- [~] Multiline macro bodies via `\` line splice (subset) — `tests/test_preprocessor_function_like_multiline.py`
- [~] Argument macro expansion (subset) — `tests/test_preprocessor_function_like_arg_expansion.py`

### TODO (gap)
- [ ] Variadic macros (C99+, but common): `...` / `__VA_ARGS__`
- [ ] Full parameter substitution tokenization rules (no regex word-boundary hacks)
- [ ] Full hide-set / rescanning semantics for both object-like and function-like
- [ ] Expand macros across multiple tokens while preserving token boundaries
- [ ] Correct whitespace preservation rules in macro replacement (standard)
- [ ] Disable macro expansion of macro name during its own expansion (general, not only special cases)

---

## 4) Macro operators `#` and `##` (priority: P1)

### Implemented (subset)
- [~] `#` stringize basic behavior — `tests/test_preprocessor_macro_operators.py`
- [~] `#` does not expand macro argument — `tests/test_preprocessor_macro_operators.py`
- [~] `#` whitespace normalization (subset) — `tests/test_preprocessor_macro_stringize_whitespace.py`
- [~] `#` escaping for `\\` and `\"` in output — `tests/test_preprocessor_macro_stringize_escapes.py`
- [~] `##` token paste basic — `tests/test_preprocessor_macro_operators.py`
- [~] `##` args not expanded pre-paste (subset) — `tests/test_preprocessor_macro_token_paste_args_not_expanded.py`
- [~] `##` pasted result best-effort rescanned — `tests/test_preprocessor_macro_token_paste_rescan.py`

### TODO (gap)
- [ ] Full stringize escaping rules (tabs/newlines, trigraph interactions, etc.)
- [ ] Full token-paste legality rules + diagnostics for invalid results
- [ ] `##` at start/end of replacement list
- [ ] `##` with empty arguments (requires variadics)

---

## 5) Conditional expressions in `#if` / `#elif` (priority: P0)

### Implemented (subset)
- [~] `defined X` / `defined(X)` and `!defined(...)` — `tests/test_preprocessor_defined.py`
- [x] `defined(NAME)` argument is not macro-expanded — `tests/test_preprocessor_defined_defined_macro_expansion.py`
- [~] Identifiers: undefined => 0; defined numeric => value (subset) — `tests/test_preprocessor_if_expr.py`, `tests/test_preprocessor_if_expr_undefined_id_is_0.py`
- [~] Operators (large subset):
  - [~] unary `! ~ + -`
  - [~] `* / %` and `+ -`
  - [~] `<< >>`
  - [~] `< > <= >=` and `== !=`
  - [~] `& ^ |` and `&& ||`
  - [~] `?:` and `,`
  — see the `tests/test_preprocessor_if_*.py` files
- [~] Literals: decimal/hex/octal integers — `tests/test_preprocessor_if_numeric_bases.py`
- [~] Character constants incl. escapes + multi-char subset — `tests/test_preprocessor_if_char_literals_*.py`

### TODO (gap)
- [ ] Full integer literal grammar (suffixes `U/L`, digit separators not applicable; but `0u` etc. in practice)
- [ ] Correct integer width/overflow semantics matching the host model (implementation-defined)
- [ ] Full tokenization parity with C preprocessing tokens
- [ ] `defined` inside more complex macro-expanded expressions parity with C

---

## 6) Predefined macros (priority: P1)

- [~] `__LINE__` / `__FILE__` — `tests/test_preprocessor_builtin_macros_line_file.py`
- [~] `__STDC__` — `tests/test_preprocessor_builtin_macros_c89.py`
- [~] `__DATE__` / `__TIME__` — `tests/test_preprocessor_builtin_macros_c89.py`
- [ ] C89-required behavior around `#line` affecting `__LINE__` / `__FILE__` (full)
- [ ] Other common predefined macros (not C89, but common): `__STDC_VERSION__`, `__GNUC__`, etc.

---

## 7) Line control / diagnostics (priority: P2)

- [~] `#line` accepted and stripped from `-E` output — `tests/test_preprocessor_line_directive.py`
- [~] malformed `#line` in inactive region ignored — `tests/test_preprocessor_line_directive_ignored_in_inactive.py`
- [ ] Full `#line` semantics updating logical line/file
- [ ] Diagnostics with file/line ranges (caret), include stacks
- [ ] Standard-required diagnostic wording is not targeted; just consistency + testability

---

# Priority plan (next steps)

## P0 (correctness / safety)
- [ ] Implement macro-expanded `#include` operands (very common in real code)
- [ ] Replace regex-based macro substitution with token-based substitution (unblocks correctness across many cases)
- [ ] Generalize hide-set implementation (remove special-case suppressions)

## P1 (macro completeness)
- [ ] Full `#` stringize normalization + escaping parity
- [ ] Full `##` paste legality + rescanning parity
- [ ] Variadic macros (C99+, but needed for real headers)

## P2 (tooling / diagnostics)
- [ ] Proper `#line` semantics + update `__LINE__`/`__FILE__`
- [ ] Better error messages (file/line, include stack)

---

## How to use this checklist

- For each TODO item:
  1) Add a focused failing pytest.
  2) Implement minimal code.
  3) Run full `pytest -q`.
  4) Update this checklist (mark [~] or [x]).
  5) Commit with a small, scoped message.
