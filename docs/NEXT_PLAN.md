# AuraCompiler — Next Major Refactoring Plan

> This document tracks planned architectural improvements for the next development phase.
> Updated after each major version milestone. Current baseline: cJSON 1.7.19 + sqlite3 parser 100% passing, 2059 pycc tests passing.

## ~~1. Unify local initializer lowering~~ — DONE

Completed 2026-04. Replaced ~500 lines of ad-hoc initializer lowering with unified recursive `_lower_initializer` dispatching on CType kind (ARRAY/STRUCT/UNION/Scalar). Handles brace elision, designated initializers, trailing zero-fill, string init, multi-dim arrays. 10 property-based tests validate correctness. See `.kiro/specs/initializer-lowering/`.

## 2. Remove _var_types dictionary

**Problem**: Stringly-typed dictionaries duplicating TypedSymbolTable information.

**Dependencies**: Plan 1 complete ✓.

**Scope**: Medium refactor. ~1-2 days.


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


## 6. Complete expression type annotation in semantic analysis

**Problem**: _expr_type() returns None for compound expressions, causing false positives and code duplication.

**Proposed**: Bottom-up type annotation pass computing .resolved_type for every expression node based on C89 rules. All downstream consumers read .resolved_type.

**Benefits**: Eliminates false positives, simplifies IR gen, enables multi-language frontend support.

**Scope**: Large. 500-800 lines new + ~200 lines refactoring. Standalone spec.
