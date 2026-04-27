# AuraCompiler — Next Major Refactoring Plan

> This document tracks planned architectural improvements for the next development phase.
> Updated after each major version milestone. Current baseline: cJSON 1.7.19 + sqlite3 parser 100% passing, 1825 pycc tests passing.
>
> 复杂度评估更新于 2026-04-27。

## 优先级排序

| 优先级 | 任务 | 复杂度 | 预估时间 | 依赖 |
|--------|------|--------|----------|------|
| 1 | 1. TargetInfo | 中 | 3-4h | 无 |
| 2 | 2. 初始化器统一 | 中 | 4-6h | 无 |
| 3 | 7. 表达式类型标注 | 高 | 8-12h | 无 |
| 4 | 5. 预处理器性能 | 中 | 4-12h | 无 |
| 5 | 3. 移除 _var_types | 高 | 6-8h | 任务 2 |
| 6 | 4. IR 架构重构 | 极高 | 40-60h | 任务 1 |
| 7 | 6. 128 位整数 | 中 | 4-6h | 任务 4 |

任务 1、2、7 可独立并行推进，建议优先做。

---

## 1. Unify type size computation into a target-aware abstraction

**Problem**: Both IR layer and codegen layer independently compute type sizes with hardcoded values. This works for x86-64 but breaks portability.

**Proposed design**: Introduce a `TargetInfo` class encapsulating all platform-dependent type sizes and alignments. Both IR generator and codegen receive the same instance.

**Scope**: Medium-large refactor. Should be a standalone spec.

**现状分析**: `_type_size` 在 ir.py 定义，被 ir.py (~15处)、semantics.py (~3处) 调用；codegen.py 有独立的 `_type_size_bytes`；semantics.py 有独立的 `size_align`。三套硬编码逻辑。需新建 `TargetInfo` 类，统一三处实现，修改 ~40 个调用点。

**复杂度**: 中等偏高 | **预估时间**: 3-4 小时 | **依赖**: 无


## 2. Unify local initializer lowering into a recursive, type-driven function

**Problem**: Local variable initializer lowering uses ad-hoc if/elif branches per type combination (the "whitelist" anti-pattern from lesson 4).

**Proposed design**: Single recursive entry point dispatching on CType kind (ARRAY/STRUCT/Scalar). Handles brace elision, designated initializers, trailing zero-fill.

**Prerequisites**: TypedSymbolTable (done), ast_type_to_ctype_resolved (done).

**Scope**: Medium. ~300 lines new replacing ~500 lines old.

**现状分析**: ir.py 中初始化器处理散布在多个分支（struct、array、scalar 各有独立路径）。核心是写递归 `_lower_initializer(ctype, init_list)` 替换 ~500 行 ad-hoc 分支。难点在 brace elision 和 designated initializer 边界情况。

**复杂度**: 中等 | **预估时间**: 4-6 小时 | **依赖**: 无


## 3. Remove _var_types dictionary

**Problem**: Stringly-typed dictionaries duplicating TypedSymbolTable information.

**Dependencies**: Plan 2 should be complete first.

**Scope**: Medium refactor.

**现状分析**: `_var_types` 在 ir.py ~40 处引用，codegen.py ~50 处引用（共 ~90 处）。代码注释明确说 codegen 仍依赖 `_var_types` 做函数局部类型查找，因为 TypedSymbolTable 的 scope 在 IR gen 结束后就 pop 了。需先改 TypedSymbolTable 架构让 scope 跨 IR-gen → codegen 边界持久化，再逐个替换引用。

**复杂度**: 高 | **预估时间**: 6-8 小时 | **依赖**: 任务 2


## 4. IR Architecture Refactoring: Structured, Typed, Multi-Layer IR

**Priority**: High. Core flaws: no Function/BasicBlock/CFG, target-dependent details in IR, weak typing.

**Proposed**: HIR (typed, structured) -> LIR (virtual registers, platform-specific) -> Assembly. 5 migration phases.

**Dependencies**: Plan 1 (TargetInfo) for LIR lowering.

**Scope**: Large. 2000-3000 lines across 3-5 specs.

**现状分析**: IR 是扁平 `List[IRInstruction]`，无 Function/BasicBlock/CFG。ir.py + codegen.py 合计 8000+ 行全部依赖扁平结构。这是根本性架构重写，不是单个任务而是一个项目，需 3-5 个独立 spec。

**复杂度**: 极高 | **预估时间**: 40-60 小时（分 5 阶段，每阶段 8-12h）| **依赖**: 任务 1


## 5. Preprocessor performance for large source files

**Problem**: Built-in preprocessor times out on sqlite3.c (250K lines). Forces use_system_cpp=True.

**Proposed**: Algorithm audit, PyPy compatibility, mypyc compilation.

**Scope**: Algorithm audit 1-2 days, PyPy trivial, mypyc 1 week.

**现状分析**: preprocessor.py ~1200 行。算法审计（找热点、优化宏展开/hideset）是主要工作。PyPy 兼容性基本免费。mypyc 编译需额外工作但收益大。

**复杂度**: 中等 | **预估时间**: 算法优化 4-6h，mypyc 8-12h | **依赖**: 无


## 6. Support 128-bit integers on x86-64

**Problem**: __uint128_t mapped to 64-bit (lossy). sqlite3 uses it for high-precision math.

**Proposed**: CType.INT128/UINT128, register-pair codegen using x86-64 mul/div.

**Dependencies**: Plan 4 (IR refactoring).

**Scope**: Medium. ~250 lines.

**现状分析**: 被任务 4 阻塞。单独实现约 250 行，但在当前扁平 IR 上做会很脏。

**复杂度**: 中等 | **预估时间**: 4-6 小时（假设任务 4 已完成）| **依赖**: 任务 4


## 7. Complete expression type annotation in semantic analysis

**Problem**: _expr_type() returns None for compound expressions, causing false positives and code duplication.

**Proposed**: Bottom-up type annotation pass computing .resolved_type for every expression node based on C89 rules. All downstream consumers read .resolved_type.

**Benefits**: Eliminates false positives, simplifies IR gen, enables multi-language frontend support.

**Scope**: Large. 500-800 lines new + ~200 lines refactoring. Standalone spec.

**现状分析**: `_expr_type()` ~120 行，只处理部分 AST 节点（Cast、Identifier、UnaryOp、MemberAccess、FunctionCall、ArrayAccess、部分 BinaryOp），复合表达式返回 None。需覆盖所有 C89 表达式类型推导规则（UAC、整数提升、指针算术、逗号/三元运算符等），并修改所有下游消费者。

**复杂度**: 高 | **预估时间**: 8-12 小时 | **依赖**: 无
