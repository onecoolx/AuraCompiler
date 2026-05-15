# AuraCompiler — Next Major Refactoring Plan

> This document tracks planned architectural improvements for the next development phase.
> Updated: 2026-05-18. Baseline: 2692 pycc tests passing, expression type annotation and _var_types removal complete.

---

## ~~1. Complete expression type annotation in semantic analysis~~ ✅ DONE

Completed 2026-05-14. Spec: `.kiro/specs/expr-type-annotation/`. All 17 correctness properties verified via Hypothesis PBT. IR generator now reads `.resolved_type` for Cast, BinaryOp pointer arithmetic, and FunctionCall return type.

---

## ~~2. Remove _var_types dictionary~~ ✅ DONE

Completed 2026-05-18. Spec: `.kiro/specs/remove-var-types/`. 6 correctness properties verified via Hypothesis PBT.

**Result**:
- `_var_types` fully removed from `CodeGenerator` — all type queries use `TypedSymbolTable` (CType-based)
- `_var_types` writes remain in `IRGenerator` for two methods that still need string-based type info:
  - `_operand_type_string`: function pointer types (e.g. `"int (*)(int)"`) cannot be accurately represented by `ctype_to_ir_type` yet
  - `_is_function_pointer_operand`: uses `"(*)"` pattern matching on `_var_types` strings as fallback
- All IR generator type READS use `_sym_table` exclusively; `_var_types` is write-only (for codegen compatibility during the transition)
- Full removal of IR generator `_var_types` is blocked on adding `FunctionTypeCType` support to `ctype_to_ir_type`

**Migration stats**: 104 codegen references eliminated, IR generator reads fully migrated to CType-based queries. 2692 tests passing, cJSON and Lua integration tests verified.

---

## 3. IR Architecture Refactoring: Structured, Typed, Multi-Layer IR

**Problem**: Current IR is a flat list of `IRInstruction` with no Function/BasicBlock/CFG structure. Target-dependent details (register names, ABI conventions) leak into IR generation. No SSA form.

**Proposed**: HIR (typed, structured) → LIR (virtual registers, platform-specific) → Assembly. 5 migration phases.

**Dependencies**: TargetInfo (done). Plan 2 ✅ (clean type system established).

**Complexity**: Very large. 2000-3000 lines across 3-5 specs. Fundamental architecture change.
**Estimated time**: 40-60h (multiple weeks).

---

## 4. Preprocessor performance for large source files

**Problem**: Built-in preprocessor times out on sqlite3.c (250K lines). Forces `use_system_cpp=True` for real projects.

**Proposed**:
- Algorithm audit: identify O(n²) patterns in macro expansion and include handling
- PyPy compatibility: ensure no CPython-specific patterns block PyPy JIT
- Optional: mypyc compilation of hot paths

**Dependencies**: None.

**Complexity**: Medium. Algorithm audit is the core work; PyPy/mypyc are incremental.
**Estimated time**: 8-16h for algorithm audit, +4h for PyPy, +16h for mypyc.

---

## 5. Support 128-bit integers on x86-64

**Problem**: `__uint128_t` mapped to 64-bit (lossy). sqlite3 uses it for high-precision math.

**Proposed**: Add `CType.INT128/UINT128`, register-pair codegen using x86-64 mul/div idioms.

**Dependencies**: Plan 3 (IR refactoring) — register pairs need structured IR to express cleanly.

**Complexity**: Medium. ~250 lines of type system + ~400 lines of codegen.
**Estimated time**: 8-12h.

---

## Prioritization & Next Task Recommendation

| Plan | Complexity | Time Est. | Dependencies | Value |
|------|-----------|-----------|--------------|-------|
| ~~2. Remove _var_types~~ | ~~Large~~ | ~~16-24h~~ | ✅ Done | ✅ Done |
| 4. Preprocessor perf | Medium | 8-16h | None | Medium — only matters for large files |
| 3. IR restructuring | Very Large | 40-60h | Plan 2 ✅ | Very High — Plan 2 done, path is clear |
| 5. 128-bit integers | Medium | 8-12h | Plan 3 | Low priority — niche use case |

**Recommended next**: **Plan 3 (IR Architecture Refactoring)**

Rationale:
- Plan 1 ✅ and Plan 2 ✅ are both complete — all prerequisites satisfied
- Plan 3 is the biggest architectural win: structured IR with Function/BasicBlock/CFG
- TypedSymbolTable is now the single source of truth for type info in codegen, making IR restructuring cleaner
- Alternatively, Plan 4 (preprocessor perf) is a smaller independent task if a shorter project is preferred
