# AuraCompiler — Next Major Refactoring Plan

> This document tracks planned architectural improvements for the next development phase.
> Updated: 2026-05-13. Baseline: 2381 pycc tests passing, initializer architecture rewrite complete.

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
