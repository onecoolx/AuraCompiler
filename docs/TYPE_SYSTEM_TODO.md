# Type & Semantics TODO (C89 target)

Last updated: 2026-03-30

This is a **working engineering checklist** for completing the C89 type system and semantic rules in `pycc/`.
It is organized by capability area, and intended to be driven by **tests-first** changes.

## 1) Core type representation

- [ ] Define a single canonical representation for types used across parser/semantics/IR:
  - [ ] integer base types: `char/short/int/long` and `signed/unsigned` combinations
  - [ ] qualifiers: `const/volatile` on base and per-pointer level
  - [ ] pointers: multi-level, with per-level qualifiers
  - [ ] arrays: element type, dimensions (including unknown outer dimension in init contexts)
  - [ ] functions: return type, parameter types, prototype vs non-prototype, variadic
- [ ] Composite type rule helpers:
  - [ ] `is_scalar`, `is_integer`, `is_arithmetic`, `is_object`, `is_function`, `is_incomplete`, `is_modifiable_lvalue`

## 2) Constant expressions (ICE)

- [ ] Unified ICE evaluator in `semantics` (used for enum, switch/case, array sizes, bitfields)
- [ ] C89 constraints:
  - [ ] allow `sizeof(type-name)` as ICE
  - [ ] reject `sizeof(expression)` as ICE
  - [ ] allow enum constants
  - [ ] cover unary/binary ops, ternary, comma (subset) consistently

## 3) Integer promotions & usual arithmetic conversions

- [ ] Implement full integer promotions
- [ ] Implement usual arithmetic conversions for all integer pairs (signed/unsigned, widths)
- [ ] Apply consistently in:
  - [ ] arithmetic ops
  - [ ] bitwise ops
  - [ ] comparisons
  - [ ] conditional operator `?:`
  - [ ] shifts (incl. shift count type)

## 4) Pointer conversions & compatibility

- [ ] Null pointer constants
- [ ] `void*` conversions
- [ ] Qualified pointer conversions (multi-level)
- [ ] Function pointers: type compatibility (not only arity)
- [ ] Composite pointer types and assignment constraints

## 5) Arrays & functions

- [ ] Array decay rules and exceptions (`sizeof`, `&`, string literals)
- [ ] Function designator decay
- [ ] Parameter adjustments (array->pointer, function->pointer)
- [ ] Prototype vs K&R non-prototype call rules (default promotions)

## 6) Aggregates (struct/union/enum)

- [ ] Incomplete types + forward declarations
- [ ] Member access typing and lvalue rules
- [ ] Assignment and parameter passing constraints
- [ ] Enum typing as `int` and range checks

## 7) Lvalue rules and assignments

- [ ] Modifiable lvalue enforcement
- [ ] `const` and `volatile` constraints
- [ ] compound assignments, `++/--`

## 8) Control-flow typing constraints

- [ ] Scalar controlling expressions (`if/while/for/switch`)
- [ ] `break/continue` placement constraints
- [ ] `goto` label constraints (function scope)

## 9) sizeof semantics (beyond ICE)

- [ ] Reject sizeof(function type)
- [ ] Reject sizeof(incomplete type)
- [ ] Validate sizeof on arrays/pointers/objects

## 10) Diagnostics

- [ ] Ensure semantic diagnostics are stable, unified, and tested.

---

## Notes about current implementation

- `enum` values: minimal ICE evaluator exists in `SemanticAnalyzer._eval_const_int`.
- `switch` case ICE: currently enforced in IR lowering via `_eval_const_int_expr`.
- `sizeof` lowering: currently best-effort in IR; semantics needs to become the source of truth.
