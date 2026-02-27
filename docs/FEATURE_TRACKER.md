# AuraCompiler Feature Tracker (Living)

Last updated: 2026-02-26

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
- **PARTIAL** storage class (`static`/`extern`/`auto`/`register` subset + `&register` rejected + `extern` initializer rejected + local `static` rejected) — `tests/test_storage_class.py`, `tests/test_auto_register.py`, `tests/test_extern_initializer.py`, `tests/test_local_static.py`
- **PARTIAL** full declarator grammar (function pointers etc.) — TODO
- **PARTIAL** `const` qualifier: reject assignment and compound assignment to const locals/globals (subset) — `tests/test_const.py`
- **PARTIAL** `const` qualifier: reject assignment through `*p` when `p` is const-qualified pointer (subset) — `tests/test_const_pointer.py`
- **PARTIAL** function pointer local declarations + indirect calls (subset) — `tests/test_declarators.py`
- **PARTIAL** array of function pointers declarator (subset) — `tests/test_declarators.py`
- **PARTIAL** function pointer parameters (subset) — `tests/test_declarators.py`
- **PARTIAL** functions returning function pointers (subset; incl. prototype/extern) — `tests/test_declarators.py`
- **PARTIAL** function redeclaration compatibility checks (subset: return type + param count) — `tests/test_function_decl_compat.py`

### Expressions / Operators

- **DONE** arithmetic/bitwise/compare/assignment/calls/?: — covered across many tests
- **DONE** `sizeof` (subset) — `tests/test_sizeof.py`
- **DONE** C-style cast (subset) — `tests/test_cast.py`
- **DONE** `&&`/`||` short-circuit — `tests/test_short_circuit.py`
- **PARTIAL** comma operator `,` (expression + for-clause) — `tests/test_comma_operator.py`
- **PARTIAL** reject `void` objects/parameters (subset) — `tests/test_void_type.py`
- **PARTIAL** conditional operator (`?:`) usual arithmetic conversions (unsigned int/unsigned long cases) — `tests/test_int_conversions.py`
- **PARTIAL** integer promotions + usual arithmetic conversions — comparisons for `int` vs `unsigned int` (best-effort) — `tests/test_int_conversions.py`
- **PARTIAL** usual arithmetic conversions involving `unsigned long` (tests) — `tests/test_int_conversions.py`
- **PARTIAL** unsigned `unsigned long` division/modulo semantics (tests) — `tests/test_int_conversions.py`
- **PARTIAL** unsigned 32-bit arithmetic wrap for `+/-/*` (best-effort; fixed reg-clobber in codegen) — `tests/test_int_conversions.py`
- **PARTIAL** unsigned 32-bit division/modulo for `/` and `%` (best-effort) — `tests/test_int_conversions.py`
- **PARTIAL** shift semantics: unsigned `>>` logical, signed `>>` arithmetic (best-effort) — `tests/test_int_conversions.py`
- **PARTIAL** compound assignment conversions for `unsigned int` (best-effort) — `tests/test_int_conversions.py`
- **PARTIAL** integer promotions for `short`/`unsigned short` (tests) — `tests/test_int_conversions.py`
- **PARTIAL** integer promotions: sign/zero extension for `char`/`short` and basic comparisons (tests) — `tests/test_integer_promotions_more.py`
- **PARTIAL** comparisons involving `short`/`unsigned short` after promotions (tests) — `tests/test_int_conversions.py`
- **PARTIAL** assignment narrowing/truncation for `char`/`short` (tests) — `tests/test_int_conversions.py`
- **PARTIAL** load sign/zero extension for `char`/`short` (tests) — `tests/test_int_conversions.py`
- **PARTIAL** compound assignment truncation for `char`/`short` (tests) — `tests/test_int_conversions.py`
- **PARTIAL** pointer arithmetic completeness — `tests/test_pointer_arith.py` (more TODO)

### Statements / Control Flow

- **DONE** if/while/do/for — integration tests
- **PARTIAL** switch/case/default (subset; duplicate `case`/multiple `default` rejected) — `tests/test_switch.py`, `tests/test_switch_semantics.py`
- **DONE** break/continue — integration tests
- **DONE** goto/labels — `tests/test_goto.py`

### Initialization / Data

- **PARTIAL** global string literal pointer init — `tests/test_global_string_ptr.py`
- **PARTIAL** local array initializers (non-designated): `int a[N] = {..}` and zero-fill, plus `char s[] = "..."` — `tests/test_initializers.py`
- **PARTIAL** local fixed-size char array string init: `char s[N] = "..."` (incl. implicit terminator + trailing zero-fill) — `tests/test_initializers.py`
- **PARTIAL** truncation for fixed-size char array string init when no room for terminator — `tests/test_initializers.py`
- **PARTIAL** local fixed-size char array brace init zero-fill: `char s[N] = {...}` — `tests/test_initializers.py`
- **PARTIAL** `sizeof` on local arrays returns byte size (best-effort) — `tests/test_initializers.py`
- **PARTIAL** character literals (`'a'`) in expressions (lowered as `int`, best-effort escapes TBD) — covered across `tests/test_initializers.py` and others
- **PARTIAL** local array size inference from brace initializer: `int a[] = {..}` (scalar-only subset) — `tests/test_initializers.py`
- **PARTIAL** inferred-size array edge cases: singleton initializer `{1}` infers length 1 — `tests/test_initializers.py`
- **PARTIAL** fixed-size array brace init truncates extra elements (best-effort) — `tests/test_initializers.py`
- **PARTIAL** local array size inference from brace initializer: `char s[] = {...}` (scalar-only subset) — `tests/test_initializers.py`
- **PARTIAL** local struct brace initializers (non-designated): `struct S x = { ... }` with member-order init + zero-fill — `tests/test_struct_initializers.py`
- **PARTIAL** global aggregate initializers (subset): fixed-size `int[]`/`char[]` (brace + string) and `struct` brace init (member-order + zero-fill) via `.data` blobs — `tests/test_global_aggregate_initializers.py`

---

## Milestone 2 — Preprocessor + Multi-file + glibc

- **PARTIAL** Preprocessor stage (`-E`) (subset: passthrough + local `#include "file"` + object-like `#define` + `#undef` + `#ifdef/#ifndef` + `#if 0/1` and `#if NAME` (NAME expands to 0/1) with `#elif 0/1` and `#elif NAME` + `#else`) — `tests/test_preprocessor_E.py`, `tests/test_preprocessor_include.py`, `tests/test_preprocessor_define.py`, `tests/test_preprocessor_undef.py`, `tests/test_preprocessor_ifdef.py`, `tests/test_preprocessor_if0.py`, `tests/test_preprocessor_if_macro.py`, `tests/test_preprocessor_else.py`, `tests/test_preprocessor_elif.py`
- (tests) nested conditional handling — `tests/test_preprocessor_nested_conditionals.py`
- (tests) directive whitespace tolerance — `tests/test_preprocessor_directive_whitespace.py`
- **PARTIAL** Preprocessor `#ifndef` directive (subset): conditional inclusion when macro is undefined — `tests/test_preprocessor_ifndef.py`
- **PARTIAL** Preprocessor `defined` in `#if/#elif` (subset): `defined(X)` / `defined X` and negated forms — `tests/test_preprocessor_defined.py`
- **PARTIAL** Preprocessor `#elifdef/#elifndef` directives (subset): `#elifdef X` and `#elifndef X` — `tests/test_preprocessor_elifdef_elifndef.py`
- **PARTIAL** Preprocessor `#if` expression evaluation (subset): `!`, `&&`, `||`, `==`, `!=`, `+`, `-`, parentheses, integers, identifiers (best-effort) — `tests/test_preprocessor_if_expr.py`
- **PARTIAL** Preprocessor `#elif` expression evaluation (subset): `#elif <expr>` using same evaluator as `#if` — `tests/test_preprocessor_elif_expr.py`
- **PARTIAL** Preprocessor rejects `#include_next` (subset): fail fast with explicit error — `tests/test_preprocessor_include_next.py`
- **PARTIAL** Preprocessor `#pragma once` (subset): strip from output + honor include-once semantics (active-region only) — `tests/test_preprocessor_pragma_once.py`, `tests/test_preprocessor_include_guards.py`, `tests/test_preprocessor_pragma_once_edges.py`
- (tests) `#pragma once` breaks mutual include cycles (subset) — `tests/test_preprocessor_include_cycle_pragma_once.py`
- (tests) `#pragma once` path equivalence (same file, different include spellings) — `tests/test_preprocessor_pragma_once_path_equivalence.py`
- (tests) `#pragma once` symlink/realpath equivalence (subset) — `tests/test_preprocessor_pragma_once_symlink.py`
- **PARTIAL** Preprocessor strips comments (subset): `//` and `/* ... */` (incl. multiline) — `tests/test_preprocessor_comments.py`
- **PARTIAL** Preprocessor rescans object-like macros (subset): chained defines expand to fixed point (bounded; cycle-safe) — `tests/test_preprocessor_macro_rescan.py`, `tests/test_preprocessor_macro_cycle.py`
- **PARTIAL** Preprocessor `#error` directive (subset): fail when active, ignore in skipped regions — `tests/test_preprocessor_error_directive.py`
- **PARTIAL** Preprocessor `#warning` directive (subset): accept and strip from output — `tests/test_preprocessor_warning_directive.py`
- **PARTIAL** Preprocessor `#undef` directive (subset): removes object-like and function-like macros — `tests/test_preprocessor_undef.py`
- **PARTIAL** Preprocessor angle-bracket includes (subset): `#include <...>` via `-I` and system include probing — `tests/test_preprocessor_include_angle.py`
- **PARTIAL** Preprocessor `#line` directive (subset): accept and strip from `-E` output — `tests/test_preprocessor_line_directive.py`
- **PARTIAL** Preprocessor function-like macros (subset): `#define F(x) ...` + invocation expansion (incl. nested calls) — `tests/test_preprocessor_function_like_macros.py`
- **PARTIAL** Preprocessor multiline function-like macros (subset): `#define F(x) ... \\` line continuation in macro body — `tests/test_preprocessor_function_like_multiline.py`
- **PARTIAL** Preprocessor expands function-like macro arguments (subset): e.g. `INC(B)` where `B` is a macro — `tests/test_preprocessor_function_like_arg_expansion.py`
- **PARTIAL** Preprocessor macro operators (subset): `#` (stringize) and `##` (token paste) — `tests/test_preprocessor_macro_operators.py`
- **PARTIAL** Preprocessor macro expansion safety (subset): no expansion inside string/char literals; identifier-only substitution — `tests/test_preprocessor_macro_expansion_edges.py`
- **PARTIAL** Preprocessor predefined macros (subset): `__LINE__`, `__FILE__` — `tests/test_preprocessor_builtin_macros_line_file.py`
- **PARTIAL** Preprocessor predefined macros (subset): `__LINE__`, `__FILE__`, `__STDC__`, `__DATE__`, `__TIME__` — `tests/test_preprocessor_builtin_macros_line_file.py`, `tests/test_preprocessor_builtin_macros_c89.py`
- **PARTIAL** Preprocessor predefined macros (subset): `__LINE__`, `__FILE__`, `__STDC__`, `__DATE__`, `__TIME__`, `__COUNTER__` (per-instance monotonic counter) — `tests/test_preprocessor_builtin_macros_line_file.py`, `tests/test_preprocessor_builtin_macros_c89.py`, `tests/test_preprocessor_counter.py`
- **PARTIAL** Preprocessor multiline object-like `#define` (subset): line continuation with trailing `\\` — `tests/test_preprocessor_define_multiline.py`
- **PARTIAL** Driver supports multiple inputs (subset): `pycc.py file1.c file2.c -o a.out` — `tests/test_driver_multi_file_cli.py`
- **PARTIAL** Multi-input + `--use-system-cpp` (glibc headers + multi-TU link) — `tests/test_driver_multi_file_system_cpp.py`
- **PARTIAL** Emit `.o` and link multiple translation units with system `gcc` (no-pie subset) — `tests/test_multi_tu.py`
- **PARTIAL** Preprocessor wired into normal compilation (subset: `#include` + basic conditionals/macros) — `tests/test_compile_with_preprocessor.py`
- **PARTIAL** `-D/-U` macros affect compilation preprocessing (subset) — `tests/test_compile_with_D_U.py`
- **PARTIAL** `--use-system-cpp` forwards `-I/-D/-U` for normal compilation (subset) — `tests/test_driver_system_cpp_DIU_compile.py`
- **PARTIAL** glibc smoke test via `<stdio.h>` (skips if system include dirs not configured) — `tests/test_glibc_smoke_stdio.py`
- **PARTIAL** `--use-system-cpp`: preprocess with system `gcc -E -P` for better system header compatibility (passes `<stdio.h>` integration: `puts`/`printf`) — `tests/test_glibc_system_cpp_stdio.py`, `tests/test_glibc_system_cpp_printf.py`
- **PARTIAL** system include path probing via `gcc -E -Wp,-v -` (best-effort) — `tests/test_preprocessor_gcc_include_probe.py`
- Tests:
  - `tests/test_preprocessor_*.py`
  - `tests/test_multi_tu.py`
  - `tests/test_multifile_linking.py`

---

## Milestone 3 — Strict C89 coverage

- **TODO** tighten semantics & diagnostics (compatible redecls, incomplete types, qualifier rules, etc.)
- **TODO** conformance corpus and gcc comparison runs

---

## Milestone 4 — gcc/clang-compatible driver

- **PARTIAL** CLI parity (subset): `-c`, `-S`, `-E`, `-o`, `-I`, `-D`, `-U`, `-std=`, `-Wall/-Werror`, `-O0/-O1` (subset: `-D/-U/-I` for `-E`) — `tests/test_preprocessor_D.py`, `tests/test_preprocessor_U.py`, `tests/test_preprocessor_I.py`
  - `--use-system-cpp -E` (preprocess-only via gcc) — `tests/test_driver_system_cpp_E.py`

---

## Milestone 5 — Diagnostics

- **TODO** consistent English diagnostics (source ranges, notes, carets)
- **TODO** error codes/categories, and test expectations for error messages
