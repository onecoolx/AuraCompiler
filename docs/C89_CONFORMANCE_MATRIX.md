# C89 Conformance Matrix (stub)

Last updated: 2026-04-08

Purpose:
- Provide a **spec-area ↔ tests ↔ status** map.
- Reduce ambiguity when planning phases and reviewing regressions.

Rule:
- Status must be justified by at least one test file.

Legend: **DONE** / **PARTIAL** / **TODO**.

Snapshot (source of truth):
- `pytest -q`: **947 passed** (as of 2026-04-08)

## Frontend

| Area | Status | Tests / Notes |
|---|---:|---|
| Lexing (tokens, literals, comments) | DONE | `tests/test_lexer.py` |
| Preprocessing: includes | DONE | driver + preprocessor tests; see many `tests/test_preprocessor_*.py` |
| Preprocessing: macros | DONE | `tests/test_preprocessor_define*.py`, `tests/test_preprocessor_function_like_macros.py`, `tests/test_preprocessor_variadic_macros.py` |
| Preprocessing: conditional compilation (`#if`) | DONE | `tests/test_preprocessor_if_*.py` + `tests/test_preprocessor_if_numeric_suffix_and_fn_macro.py` |

## Declarations / Types

| Area | Status | Tests / Notes |
|---|---:|---|
| `typedef` | DONE | `tests/test_typedef.py` |
| `struct`/`union` layout | DONE | `tests/test_struct_union.py` |
| member access `.` / `->` | DONE | `tests/test_member_access.py`, `tests/test_member_semantics.py` |
| storage classes (`static/extern/auto/register`) | DONE | `tests/test_storage_class*.py`, `tests/test_auto_register.py`, `tests/test_local_static.py`, `tests/test_local_static_basic.py` |
| qualifiers (`const/volatile`) | PARTIAL | `tests/test_const.py`, `tests/test_const_pointer.py`, `tests/test_volatile_semantics.py`; volatile codegen not honored |
| builtin types (`__builtin_va_list`) | DONE | parsing + codegen: `tests/test_builtin_va_list_parsing.py`, `tests/test_varargs_*.py` |
| array declarators + inferred sizes | DONE | `tests/test_multi_dim_array_infer_inner_dim_from_initializer.py`, `tests/test_initializers.py` |

## Expressions / Semantics

| Area | Status | Tests / Notes |
|---|---:|---|
| integer promotions / UAC | DONE | `tests/test_integer_promotions_*.py`, `tests/test_int_conversions*.py`, `tests/test_usual_arithmetic_conversions*.py` |

Notes:
- LP64 usual arithmetic conversion case `long` vs `unsigned int` is covered by `tests/test_usual_arithmetic_conversions_long_vs_unsigned_int.py`.
| pointer arithmetic | DONE | `tests/test_pointer_arith*.py` |
| `sizeof` | DONE | `tests/test_sizeof*.py` |
| short-circuit `&&/||` | DONE | `tests/test_short_circuit.py` |
| `++`/`--` operators | DONE | `tests/test_increment_decrement.py` |

## Runtime / ABI

| Area | Status | Tests / Notes |
|---|---:|---|
| SysV call alignment | DONE | integration tests + varargs tests |
| varargs `%al` | DONE | `tests/test_variadic_printf_local_extern_proto.py` |
| float params xmm0-xmm7 | DONE | codegen supports all 8 xmm arg registers |
| `va_list` pass to libc | DONE | `tests/test_varargs_va_list_pass_to_libc_vsnprintf.py` |

## glibc / system headers (smoke)

| Area | Status | Tests / Notes |
|---|---:|---|
| `<stdio.h>` smoke: `puts` | DONE | `tests/test_glibc_smoke_stdio.py` |
| `<stdio.h>` smoke: `printf` | DONE | `tests/test_glibc_smoke_stdio_printf.py` |
| `<stdio.h>` smoke: `snprintf` | DONE | `tests/test_glibc_smoke_stdio_snprintf.py` |
| `<stdarg.h>` smoke: `va_list` + `va_start`/`va_end` + `vsnprintf` | DONE | `tests/test_glibc_smoke_stdarg_vsnprintf.py` |

## Arrays (multi-dimensional)

| Area | Status | Tests / Notes |
|---|---:|---|
| 2D array decay to pointer-to-row | DONE | `tests/test_multi_dim_array_decay.py` |
| `sizeof` for local 2D arrays | DONE | `tests/test_sizeof_array_vs_pointer.py` |
| nested indexing `a[i][j]` | DONE | `tests/test_multi_dim_array_init_and_index.py` |
| `<errno.h>` smoke: `errno` read/write | DONE | `tests/test_glibc_smoke_errno_basic.py` |
| `<string.h>` smoke: `strlen` | DONE | `tests/test_glibc_smoke_string_strlen.py` |
| `<string.h>` smoke: `memcpy` | DONE | `tests/test_glibc_smoke_string_memcpy.py` |
| `<string.h>` smoke: `memcmp` | DONE | `tests/test_glibc_smoke_string_memcmp.py` |
| `<string.h>` smoke: `memset` | DONE | `tests/test_glibc_smoke_string_memset.py` |

## Next actions

- Expand this matrix incrementally as features land.
- When a feature is added, add/update a row and link the proving tests.
