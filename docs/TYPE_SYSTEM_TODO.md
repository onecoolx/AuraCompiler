# Type & Semantics TODO (C89 target)

Last updated: 2026-04-08

This is a **working engineering checklist** for completing the C89 type system and semantic rules in `pycc/`.
It is organized by capability area, and intended to be driven by **tests-first** changes.

## 1) Core type representation

- [x] Define a single canonical representation for types used across parser/semantics/IR:
  - [x] integer base types: `char/short/int/long` and `signed/unsigned` combinations
  - [x] qualifiers: `const/volatile` on base and per-pointer level
  - [x] pointers: multi-level, with per-level qualifiers
  - [x] arrays: element type, dimensions (including unknown outer dimension in init contexts)
  - [x] functions: return type, parameter types, prototype vs non-prototype, variadic
- [x] Composite type rule helpers:
  - [x] `is_scalar`, `is_integer`, `is_arithmetic`, `is_object`, `is_function`, `is_incomplete`, `is_modifiable_lvalue`

## 2) Constant expressions (ICE)

- [x] Unified ICE evaluator in `semantics` (used for enum, switch/case, array sizes, bitfields)
- [x] C89 constraints:
  - [x] allow `sizeof(type-name)` as ICE
  - [x] reject `sizeof(expression)` as ICE
  - [x] allow enum constants
  - [x] cover unary/binary ops, ternary, comma (subset) consistently

## 3) Integer promotions & usual arithmetic conversions

- [x] Implement full integer promotions
- [x] Implement usual arithmetic conversions for all integer pairs (signed/unsigned, widths)
- [x] Apply consistently in:
  - [x] arithmetic ops
  - [x] bitwise ops
  - [x] comparisons
  - [x] conditional operator `?:`
  - [x] shifts (incl. shift count type)

## 4) Pointer conversions & compatibility

- [x] Null pointer constants
- [x] `void*` conversions
- [x] Qualified pointer conversions (multi-level)
- [ ] Function pointers: type compatibility (param types, not only arity)
- [x] Composite pointer types and assignment constraints

## 5) Arrays & functions

- [x] Array decay rules and exceptions (`sizeof`, `&`, string literals)
- [x] Function designator decay
- [x] Parameter adjustments (array->pointer, function->pointer)
- [x] Prototype vs K&R non-prototype call rules (default promotions)

## 6) Aggregates (struct/union/enum)

- [x] Incomplete types + forward declarations
- [x] Member access typing and lvalue rules
- [ ] Assignment and parameter passing constraints (struct by-value)
- [x] Enum typing as `int` and range checks

## 7) Lvalue rules and assignments

- [x] Modifiable lvalue enforcement
- [x] `const` and `volatile` constraints
- [x] compound assignments, `++/--`

## 8) Control-flow typing constraints

- [x] Scalar controlling expressions (`if/while/for/switch`)
- [x] `break/continue` placement constraints
- [x] `goto` label constraints (function scope)

## 9) sizeof semantics (beyond ICE)

- [x] Reject sizeof(function type)
- [x] Reject sizeof(incomplete type)
- [x] Validate sizeof on arrays/pointers/objects

## 10) Diagnostics

- [x] Ensure semantic diagnostics are stable, unified, and tested.

---

## Remaining TODO items

- [ ] Function pointer param type checking (not only arity)
- [ ] `struct`/`union` by-value assignment, parameter passing, return
- [ ] `volatile` codegen semantics (prevent reordering/elimination)
- [ ] `long double` type support (x87 codegen)
- [ ] `va_arg` builtin
- [ ] Designated initializers
