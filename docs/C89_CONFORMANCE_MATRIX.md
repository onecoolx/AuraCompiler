# C89 Conformance Matrix (stub)

Purpose:
- Provide a **spec-area ↔ tests ↔ status** map.
- Reduce ambiguity when planning phases and reviewing regressions.

Rule:
- Status must be justified by at least one test file.

Legend: **DONE** / **PARTIAL** / **TODO**.

## Frontend

| Area | Status | Tests / Notes |
|---|---:|---|
| Lexing (tokens, literals, comments) | DONE | `tests/test_lexer.py` |
| Preprocessing: includes | PARTIAL | driver + preprocessor tests; see many `tests/test_preprocessor_*.py` |
| Preprocessing: macros | PARTIAL | `tests/test_preprocessor_define*.py`, `tests/test_preprocessor_function_like_macros.py` |
| Preprocessing: conditional compilation (`#if`) | PARTIAL | `tests/test_preprocessor_if_*.py` + `tests/test_preprocessor_if_numeric_suffix_and_fn_macro.py` |

## Declarations / Types

| Area | Status | Tests / Notes |
|---|---:|---|
| `typedef` | DONE | `tests/test_typedef.py` |
| `struct`/`union` layout | DONE | `tests/test_struct_union.py` |
| member access `.` / `->` | DONE | `tests/test_member_access.py`, `tests/test_member_semantics.py` |
| storage classes (`static/extern/auto/register`) | PARTIAL | `tests/test_storage_class*.py`, `tests/test_auto_register.py` |
| qualifiers (`const/volatile`) | PARTIAL | `tests/test_const.py`, `tests/test_const_pointer.py` |
| builtin types (`__builtin_va_list`) | PARTIAL | parsing support: `tests/test_builtin_va_list_parsing.py` |

## Expressions / Semantics

| Area | Status | Tests / Notes |
|---|---:|---|
| integer promotions / UAC | PARTIAL | `tests/test_integer_promotions_*.py`, `tests/test_int_conversions*.py` |
| pointer arithmetic | PARTIAL | `tests/test_pointer_arith*.py` |
| `sizeof` | PARTIAL | `tests/test_sizeof.py` |
| short-circuit `&&/||` | DONE | `tests/test_short_circuit.py` |

## Runtime / ABI

| Area | Status | Tests / Notes |
|---|---:|---|
| SysV call alignment | DONE | integration tests + varargs tests |
| varargs `%al` | DONE (subset) | `tests/test_variadic_printf_local_extern_proto.py` |

## glibc / system headers (smoke)

| Area | Status | Tests / Notes |
|---|---:|---|
| `<stdio.h>` smoke: `puts` | PARTIAL | `tests/test_glibc_smoke_stdio.py` |
| `<stdio.h>` smoke: `printf` | PARTIAL | `tests/test_glibc_smoke_stdio_printf.py` |
| `<stdio.h>` smoke: `snprintf` | PARTIAL | `tests/test_glibc_smoke_stdio_snprintf.py` |
| `<stdio.h>` smoke: `snprintf` | PARTIAL | `tests/test_glibc_smoke_stdio_snprintf.py` |

## Next actions

- Expand this matrix incrementally as features land.
- When a feature is added, add/update a row and link the proving tests.
