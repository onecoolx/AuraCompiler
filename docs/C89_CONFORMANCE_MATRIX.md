# C89 Conformance Matrix

Last updated: 2026-04-13

Source of truth: `pytest -q` — **1389 passed, 0 skipped** (incl. 34 gcc comparison tests)

Legend: **DONE** / **PARTIAL** / **TODO**

## Frontend

| Area | Status | Tests |
|---|---|---|
| Lexing (tokens, literals, comments) | DONE | `test_lexer.py` |
| Preprocessing: includes | DONE | `test_preprocessor_include*.py` |
| Preprocessing: macros (object/function-like) | DONE | `test_preprocessor_define*.py`, `test_preprocessor_function_like*.py` |
| Preprocessing: conditional compilation | DONE | `test_preprocessor_if*.py` |
| Preprocessing: `#`/`##` operators | DONE | `test_preprocessor_stringize_full.py`, `test_preprocessor_paste_full.py` |
| Preprocessing: hide-set / rescan | DONE | `test_preprocessor_hideset*.py`, `test_preprocessor_token_expand.py` |
| Preprocessing: `#line`, `#error`, `#pragma` | DONE | `test_preprocessor_line_directive*.py`, `test_preprocessor_error*.py` |

## Declarations / Types

| Area | Status | Tests |
|---|---|---|
| `typedef` | DONE | `test_typedef.py` |
| `struct`/`union` layout + member access | DONE | `test_struct_union.py`, `test_member_access.py` |
| `struct`/`union` by-value assign/param/return | DONE | `test_struct_by_value_*.py` |
| `enum` | DONE | `test_enum.py` |
| Storage classes (`static`/`extern`/`auto`/`register`) | DONE | `test_storage_class*.py` |
| `const` qualifier | DONE | `test_const.py`, `test_const_pointer.py` |
| `volatile` qualifier + codegen | DONE | `test_volatile_codegen.py`, `test_volatile_ir_marking.py` |
| `long double` (x87 FPU) | DONE | `test_long_double_*.py` |
| Designated initializers | DONE | `test_designated_init_*.py` |
| Function pointer full type checking | DONE | `test_fnptr_type_compat*.py` |
| Complex nested declarators | DONE | `test_complex_declarators.py` |
| Compatible/composite types (C89 §6.1.2.6) | DONE | `test_composite_types.py` |
| Implicit `int` return type (C89) | DONE | `test_gcc_comparison.py` |
| Multi-level pointers (`int **pp`) | DONE | `test_gcc_comparison.py` |
| 2D array brace-enclosed initializer | DONE | `test_gcc_comparison.py` |

## Expressions / Semantics

| Area | Status | Tests |
|---|---|---|
| Integer promotions / UAC | DONE | `test_integer_promotions_*.py`, `test_usual_arithmetic_conversions*.py` |
| Pointer arithmetic | DONE | `test_pointer_arith*.py` |
| `sizeof` | DONE | `test_sizeof*.py` |
| Short-circuit `&&`/`||` | DONE | `test_short_circuit.py` |
| `++`/`--` operators | DONE | `test_increment_decrement.py` |
| Comma operator | DONE | `test_comma_operator*.py` |
| Ternary `?:` | DONE | `test_ternary_*.py` |

## Runtime / ABI

| Area | Status | Tests |
|---|---|---|
| SysV ABI struct classifier (INTEGER/SSE/MEMORY) | DONE | `test_struct_classifier*.py` |
| `va_list` / `va_start` / `va_arg` / `va_end` | DONE | `test_va_arg_builtin.py` |
| Float params xmm0-xmm7 | DONE | `test_float_e2e_integration.py` |
| `long double` ABI (x87 st0) | DONE | `test_long_double_abi.py` |

## Warning System

| Area | Status | Tests |
|---|---|---|
| `-Wall` flag | DONE | `test_warning_system.py` |
| `-Werror` flag | DONE | `test_warning_system.py` |
| Missing return in non-void function | DONE | `test_warning_system.py` |
| Implicit function declaration | DONE | `test_warning_system.py` |

## gcc Correctness Comparison

34 C89 programs compiled with both pycc and gcc, all producing identical exit codes.

See `tests/test_gcc_comparison.py`.

## Non-C89 Items (not required for conformance)

| Area | Status | Notes |
|---|---|---|
| Optimizer | Stub | No-op; not required for correctness |
| Debug info (DWARF) | N/A | Not part of C89 standard |
| Compound literals (C99) | N/A | Not C89 |
