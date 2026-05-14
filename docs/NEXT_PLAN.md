# AuraCompiler — Next Major Refactoring Plan

> This document tracks planned architectural improvements for the next development phase.
> Updated: 2026-05-14. Baseline: 2599 pycc tests passing, expression type annotation complete.

---

## ~~1. Complete expression type annotation in semantic analysis~~ ✅ DONE

Completed 2026-05-14. Spec: `.kiro/specs/expr-type-annotation/`. All 17 correctness properties verified via Hypothesis PBT. IR generator now reads `.resolved_type` for Cast, BinaryOp pointer arithmetic, and FunctionCall return type.

---

## 2. Remove _var_types dictionary

**Problem**: Stringly-typed dictionary (`_var_types`) with 159 references in `ir.py` and 104 in `codegen.py` (263 total). Duplicates information already available in `TypedSymbolTable` (CType-based). String parsing like `"array(char,$4)"` and `"int*"` is fragile and error-prone.

**Dependencies**: Plan 1 ✅ (`.resolved_type` reduces string-to-CType guesswork).

**Proposed approach**:
1. Audit all 263 usage sites, categorize by purpose (type query, type registration, codegen width decision)
2. For each category, identify the CType equivalent via `_sym_table` or `.resolved_type`
3. Migrate in phases: first reads (replace string checks with CType checks), then writes (stop populating `_var_types`)
4. Final phase: delete `_var_types` entirely

**Complexity**: Large. 263 call sites across 2 files. Each site needs individual analysis.
**Estimated time**: 16-24h (3-4 focused sessions).

---

## 3. IR Architecture Refactoring: Structured, Typed, Multi-Layer IR

**Problem**: Current IR is a flat list of `IRInstruction` with no Function/BasicBlock/CFG structure. Target-dependent details (register names, ABI conventions) leak into IR generation. No SSA form.

**Proposed**: HIR (typed, structured) → LIR (virtual registers, platform-specific) → Assembly. 5 migration phases.

**Dependencies**: TargetInfo (done). Plan 2 recommended first (clean type system before restructuring IR).

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
| 2. Remove _var_types | Large | 16-24h | ✅ None | High — eliminates fragile string parsing, unblocks Plan 3 |
| 4. Preprocessor perf | Medium | 8-16h | None | Medium — only matters for large files |
| 3. IR restructuring | Very Large | 40-60h | Plan 2 recommended | Very High — but too large without Plan 2 first |
| 5. 128-bit integers | Medium | 8-12h | Plan 3 | Low priority — niche use case |

**Recommended next**: **Plan 2 (Remove _var_types)**

Rationale:
- Plan 1 is done, which was the prerequisite for Plan 2
- Plan 2 is the prerequisite for Plan 3 (the biggest architectural win)
- 263 string-typed references are a constant source of subtle bugs (经验 19, 24)
- The TypedSymbolTable + `.resolved_type` infrastructure is now mature enough to replace all string-based type queries
- Scope is large but well-bounded (two files, mechanical migration)
