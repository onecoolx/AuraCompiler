# AuraCompiler — Next Major Refactoring Plan

> This document tracks planned architectural improvements for the next development phase.
> Updated: 2026-04-28. Baseline: 2059 pycc tests passing, cJSON 1.7.19 + sqlite3 parser 100%.

## 1. Complete expression type annotation in semantic analysis

**Problem**: _expr_type() returns None for compound expressions, causing false positives and code duplication.

**Proposed**: Bottom-up type annotation pass computing .resolved_type for every expression node based on C89 rules. All downstream consumers read .resolved_type.

**Benefits**: Eliminates false positives, simplifies IR gen, enables multi-language frontend support.

**Scope**: Large. 500-800 lines new + ~200 lines refactoring. Standalone spec.


## 2. Remove _var_types dictionary

**Problem**: Stringly-typed dictionaries (256 references across ir.py + codegen.py) duplicating TypedSymbolTable information.

**Dependencies**: Plan 1 recommended first (`.resolved_type` reduces string-to-CType guesswork).

**Scope**: Large refactor. 12-16h.


## 3. IR Architecture Refactoring: Structured, Typed, Multi-Layer IR

**Priority**: High. Core flaws: no Function/BasicBlock/CFG, target-dependent details in IR, weak typing.

**Proposed**: HIR (typed, structured) -> LIR (virtual registers, platform-specific) -> Assembly. 5 migration phases.

**Dependencies**: TargetInfo (done) for LIR lowering.

**Scope**: Large. 2000-3000 lines across 3-5 specs.


## 4. Preprocessor performance for large source files

**Problem**: Built-in preprocessor times out on sqlite3.c (250K lines). Forces use_system_cpp=True.

**Proposed**: Algorithm audit, PyPy compatibility, mypyc compilation.

**Scope**: Algorithm audit 1-2 days, PyPy trivial, mypyc 1 week.


## 5. Support 128-bit integers on x86-64

**Problem**: __uint128_t mapped to 64-bit (lossy). sqlite3 uses it for high-precision math.

**Proposed**: CType.INT128/UINT128, register-pair codegen using x86-64 mul/div.

**Dependencies**: Plan 3 (IR refactoring).

**Scope**: Medium. ~250 lines.


## 6. Type system: distinguish arrays from pointers

**Problem**: `Type` dataclass has no `is_array` field. `Type(base="char", is_pointer=True, pointer_level=1)` is ambiguous — could be `char *p` or `char arr[N]` after decay. This causes:
- `_expr_type` for `ArrayAccess` can't distinguish "subscript of pointer array member" (result is still a pointer) from "subscript of plain pointer" (result is pointee type). Current workaround: `_is_scalar_expr` skips struct/union rejection for `ArrayAccess` expressions.
- `_lookup_member_type` for pointer array members returns a pointer type, then `ArrayAccess` dereferences it, incorrectly producing a non-pointer struct type.
- IR gen and codegen have separate `_local_array_names` / `_global_arrays` sets to track array-ness outside the type system.

**Current mitigations**:
- `_expr_type` for `Identifier` checks `_local_array_names`/`_global_arrays` and returns a pointer type (array decay). This fixes `BinaryOp` pointer arithmetic.
- `_is_scalar_expr` is lenient for `ArrayAccess` to avoid false positives from incorrect type inference.

**Proposed design**:
1. Add `is_array: bool = False` and `array_element_type: Optional[Type] = None` to `Type` dataclass.
2. Parser sets `is_array=True` for array declarations (already has `array_size`/`array_dims`).
3. `_expr_type` for `Identifier`: if `is_array`, return element pointer type (decay).
4. `_expr_type` for `ArrayAccess`: if base type `is_array`, return element type (preserving pointer level of element). If base type is plain pointer, dereference.
5. Remove `_local_array_names` / `_global_arrays` tracking — the type itself carries the information.
6. `_lookup_member_type` returns `Type(is_array=True, ...)` for array members, enabling correct subscript handling.

**Benefits**: Eliminates the array/pointer ambiguity at the type level. All downstream consumers (semantics, IR gen, codegen) can make correct decisions without side-channel tracking.

**Dependencies**: Plan 1 (expression type annotation) would benefit from this but is not strictly required.

**Scope**: Medium. ~200 lines Type changes + ~150 lines consumer updates. Should be a standalone spec.
