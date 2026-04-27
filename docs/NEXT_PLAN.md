# AuraCompiler — Next Major Refactoring Plan

> This document tracks planned architectural improvements for the next development phase.
> Updated after each major version milestone. Current baseline: cJSON 1.7.19 + sqlite3 parser 100% passing, 1925 pycc tests passing.

## 1. Unify local initializer lowering into a recursive, type-driven function

**Problem**: Local variable initializer lowering uses ad-hoc if/elif branches per type combination (the "whitelist" anti-pattern from lesson 4).

**Proposed design**: Single recursive entry point dispatching on CType kind (ARRAY/STRUCT/Scalar). Handles brace elision, designated initializers, trailing zero-fill.

**Prerequisites**: TypedSymbolTable (done), ast_type_to_ctype_resolved (done).

**Scope**: Medium. ~300 lines new replacing ~500 lines old.


## 2. Remove _var_types dictionary

**Problem**: Stringly-typed dictionaries duplicating TypedSymbolTable information.

**Dependencies**: Plan 1 should be complete first.

**Scope**: Medium refactor.


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
