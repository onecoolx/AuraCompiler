# C89 Implementation Roadmap

Last updated: 2026-04-08

## Current Status

- `pytest -q`: **1389 passed**
- Compiler pipeline: Preprocessor → Lexer → Parser → Semantics → IR → Optimizer → Codegen → as/ld
- Target: x86-64 SysV ABI, ELF executables via binutils

## Feature Matrix

Legend: **DONE** = implemented + tested | **PARTIAL** = subset works | **TODO** = not implemented

### Lexer / Literals

| Feature | Status | Notes |
|---------|--------|-------|
| Integer literals (dec/hex/oct) | **DONE** | incl. U/L suffixes |
| Float literals (3.14, 1e-5, 3.14f) | **DONE** | NUMBER_FLOAT token type |
| Character literals | **DONE** | incl. escape sequences |
| String literals | **DONE** | |
| Wide character L'x' | **DONE** | L prefix handled in lexer |
| Adjacent string concatenation | **DONE** | "ab" "cd" → "abcd" |
| Trigraphs | **DONE** | Translation phase 1 |

### Declarations

| Feature | Status | Notes |
|---------|--------|-------|
| Single declarator | **DONE** | `int x;` `int x = 1;` |
| Multiple declarators per statement | **DONE** | `int a, b;` `int a=1, b=2;` |
| Function prototypes + definitions | **DONE** | |
| K&R function definitions | **DONE** | `int f(a,b) int a; int b; {...}` |
| `extern` declarations | **DONE** | |
| `static` global | **DONE** | |
| `static` local | **DONE** | incl. `static int x = 0;` with constant initializer |
| `register` storage class | **DONE** | (treated as hint, address-of rejected) |
| `auto` storage class | **DONE** | |
| Bit-fields | **DONE** | Parse, layout, read/write codegen | | `struct { int x:4; }` |
| Flexible array size from init | **DONE** | `int a[] = {1,2,3};` |

### Type System

| Feature | Status | Notes |
|---------|--------|-------|
| `char` / `signed char` / `unsigned char` | **DONE** | |
| `short` / `unsigned short` | **DONE** | |
| `int` / `unsigned int` | **DONE** | |
| `long` / `unsigned long` | **DONE** | |
| `float` | **DONE** | SSE codegen |
| `double` | **DONE** | SSE2 codegen |
| `long double` | **DONE** | x87 FPU codegen (fldt/fstpt/faddp/fsubp/fmulp/fdivp) |
| `void` | **DONE** | |
| Pointers (multi-level) | **DONE** | |
| Arrays | **DONE** | |
| `struct` / `union` | **DONE** | layout, member access, nesting |
| `enum` | **DONE** | incl. explicit values |
| `typedef` | **DONE** | |
| `typedef struct { } T;` (anonymous) | **DONE** | Internal tag generation |
| `const` qualifier | **DONE** | assignment rejection, pointer compat |
| `volatile` qualifier | **DONE** | codegen emits memory access with `# volatile` markers |
| Integer promotion | **DONE** | CType-based in types.py |
| Usual arithmetic conversions | **DONE** | CType-based in types.py |
| Pointer ↔ void* implicit conversion | **DONE** | |
| Incompatible pointer rejection | **DONE** | |
| Function pointer compatibility | **DONE** | full param type + return type checking |
| `sizeof(type)` | **DONE** | Builtins, pointers, struct/union |
| `sizeof(expr)` | **DONE** | |

### Expressions & Operators

| Feature | Status | Notes |
|---------|--------|-------|
| Arithmetic `+ - * / %` | **DONE** | int and float |
| Bitwise `& \| ^ ~ << >>` | **DONE** | |
| Comparison `< <= > >= == !=` | **DONE** | int and float |
| Logical `&& \|\|` (short-circuit) | **DONE** | |
| Logical `!` | **DONE** | |
| Assignment `=` | **DONE** | |
| Compound assignment `+= -= *= /= %= &= \|= ^= <<= >>=` | **DONE** | |
| Pre-increment `++x` | **DONE** | incl. pointer scaling |
| Post-increment `x++` | **DONE** | incl. pointer scaling |
| Pre-decrement `--x` | **DONE** | incl. pointer scaling |
| Post-decrement `x--` | **DONE** | incl. pointer scaling |
| Comma operator | **DONE** | |
| Ternary `?:` | **DONE** | |
| Cast `(type)expr` | **DONE** | incl. int↔float, pointer↔integer |
| `sizeof` | **DONE** | type and expression forms |
| Address-of `&` | **DONE** | |
| Dereference `*` | **DONE** | |
| Array subscript `[]` | **DONE** | |
| Member access `. ->` | **DONE** | |
| Function call `f()` | **DONE** | |
| String literal | **DONE** | |

### Statements

| Feature | Status | Notes |
|---------|--------|-------|
| `if / else` | **DONE** | |
| `while` | **DONE** | incl. `i++` in body |
| `do-while` | **DONE** | incl. `i++` in body |
| `for` | **DONE** | incl. `i++` in update |
| `switch / case / default` | **DONE** | incl. fallthrough |
| `break` | **DONE** | |
| `continue` | **DONE** | |
| `goto / label` | **DONE** | |
| `return` (with/without value) | **DONE** | |
| Compound statement `{}` | **DONE** | nested scopes |

### Preprocessor

| Feature | Status | Notes |
|---------|--------|-------|
| `#define` object-like | **DONE** | |
| `#define` function-like | **DONE** | |
| `#undef` | **DONE** | |
| `#include "file"` | **DONE** | |
| `#include <file>` | **DONE** | |
| `#if / #elif / #else / #endif` | **DONE** | full expression eval |
| `#ifdef / #ifndef` | **DONE** | |
| `defined()` operator | **DONE** | |
| `#` stringize | **DONE** | |
| `##` token paste | **DONE** | |
| `#line` directive | **DONE** | |
| `#error` directive | **DONE** | |
| `#pragma once` | **DONE** | (extension) |
| `__LINE__ / __FILE__ / __DATE__ / __TIME__` | **DONE** | |
| `__STDC__` | **DONE** | |
| PPToken + hide-set engine | **DONE** | PPTokenizer + MacroExpander classes |
| System preprocessor mode | **DONE** | `--use-system-cpp` |

### Initialization

| Feature | Status | Notes |
|---------|--------|-------|
| Scalar initializer | **DONE** | |
| Array initializer | **DONE** | |
| Struct initializer | **DONE** | |
| Nested struct/array initializer | **DONE** | |
| `char[]` from string literal | **DONE** | |
| Float/double global initializer | **DONE** | IEEE 754 in .data |

### Floating Point

| Feature | Status | Notes |
|---------|--------|-------|
| `float` / `double` local variables | **DONE** | |
| Float literals (3.14f, 1.0) | **DONE** | .rodata + RIP-relative load |
| Float arithmetic `+ - * /` | **DONE** | SSE addss/subss/mulss/divss, SSE2 addsd/subsd/mulsd/divsd |
| Float comparison `< <= > >= == !=` | **DONE** | ucomiss/ucomisd |
| Int ↔ float cast | **DONE** | cvtsi2ss/cvtsi2sd/cvttss2si/cvttsd2si |
| Float ↔ double cast | **DONE** | cvtss2sd/cvtsd2ss |
| Mixed int+float expressions | **DONE** | Implicit promotion via UAC |
| Float function parameters | **DONE** | xmm0-xmm7 SysV ABI |
| Float function return | **DONE** | xmm0 |
| Float global variables | **DONE** | .data + RIP-relative load |
| Float unary minus `-f` | **DONE** | Works via integer negate path |

### Code Generation

| Feature | Status | Notes |
|---------|--------|-------|
| x86-64 SysV ABI | **DONE** | Integer args in rdi/rsi/rdx/rcx/r8/r9 |
| Stack frame management | **DONE** | |
| Function prologue/epilogue | **DONE** | |
| Variadic function calls | **DONE** | %al for xmm count |
| `va_list` / `va_start` / `va_end` | **DONE** | SysV AMD64 layout |
| SSE/SSE2 float ops | **DONE** | |
| Float .rodata constants | **DONE** | |
| Global data .data/.bss/.rodata | **DONE** | |
| Multi-file compilation + linking | **DONE** | |

## Completion Status

All 9 previously missing C89 features have been implemented:

1. ~~`++` / `--` operators~~ — **DONE** (commit 1de7a94)
2. ~~Multiple declarators~~ — **DONE** (commit 3513d0d)
3. ~~Adjacent string concatenation~~ — **DONE** (commit bb38c15)
4. ~~`sizeof(struct S)`~~ — **DONE** (commit 3b0750a)
5. ~~Float global initializers~~ — **DONE** (commit b7e5d34)
6. ~~`typedef struct {} T;`~~ — **DONE** (commit b121b64)
7. ~~Bit-fields~~ — **DONE** (commit d8c1f68)
8. ~~Wide character `L'x'`~~ — **DONE** (commit 1c6a78a)
9. ~~Trigraphs~~ — **DONE** (commit 841e143)

Additional bug fixes:
- Float function params via xmm registers (commit df44cbf)
- Float return values via xmm0 (commit df44cbf)
- Float unary minus via fsub from zero (commit df44cbf)
- Pointer ++/-- step size scaling (commit 9ffa267)
- Bit-field read/write codegen (commit df44cbf)

**Current: 1389 tests passed, all C89 language features implemented.**

---

## Remaining Gaps (C89 spec vs current implementation)

All C89 language features are now implemented and tested. The following are
non-C89 quality-of-life items:

- Optimizer is a no-op stub (does not affect correctness)
- No DWARF debug info generation
- Compound literals (C99, not C89)

### Must-have for C89 conformance

| # | Feature | Category | Effort | Notes |
|---|---------|----------|--------|-------|
| 1 | `struct`/`union` by-value assignment | Semantics + Codegen | Medium | `struct S a = b;` `a = b;` — no memcpy-style copy |
| 2 | `struct`/`union` by-value parameter passing | Codegen + ABI | Medium | SysV ABI: small structs in regs, large on stack |
| 3 | `struct`/`union` by-value return | Codegen + ABI | Medium | SysV ABI: small structs in rax/rdx, large via hidden ptr |
| 4 | `va_arg` builtin | Codegen | Medium | Can pass `va_list` to libc but cannot extract args in user variadic functions |
| 5 | `long double` type | IR + Codegen | Medium | Needs x87 FPU instructions (fld/fstp/fadd etc.) |
| 6 | `volatile` codegen semantics | Codegen | Low | Prevent load/store reordering/elimination for volatile accesses |
| 7 | Designated initializers | Parser + IR | Medium | `.member = val` and `[index] = val` — AST node defined but not implemented |
| 8 | Function pointer param type checking | Semantics | Low | Currently only checks arity, not param types |
| 9 | Reject non-constant `static` local init | IR | Low | `static int x = f();` should be rejected (C89 requires ICE) |

### Preprocessor gaps (standards-accurate)

| # | Feature | Priority | Notes |
|---|---------|----------|-------|
| 1 | Token-based macro expansion engine | P0 | Replace regex-based substitution with preprocessing-token model |
| 2 | Generalized hide-set implementation | P0 | Remove special-case suppressions |
| 3 | Full `#` stringize escaping | P1 | tabs, newlines, trigraph interactions |
| 4 | Full `##` token paste legality + diagnostics | P1 | |
| 5 | `#if` integer width/overflow semantics | P1 | Implementation-defined but should be consistent |
| 6 | Full preprocessing-token grammar | P1 | |
| 7 | Correct whitespace preservation in macro replacement | P2 | |
| 8 | Diagnostic caret ranges | P2 | |

### Nice-to-have (quality / tooling)

| # | Feature | Notes |
|---|---------|-------|
| 1 | Optimizer passes | Currently a no-op stub (20 LOC); const folding, DCE, CSE all TODO |
| 2 | `-Wall`/`-Werror` warning system | No warning infrastructure |
| 3 | Debug info (`-g` / DWARF) | Not implemented |
| 4 | gcc conformance test suite | No systematic comparison |
| 5 | Compound literals (C99) | AST node defined but not implemented |

## Quantified Summary

| Category | Items | Done | Partial | TODO | Completion |
|----------|-------|------|---------|------|------------|
| Lexer / Literals | 7 | 7 | 0 | 0 | **100%** |
| Declarations | 11 | 11 | 0 | 0 | **100%** |
| Type System | 22 | 19 | 2 | 1 | **~91%** |
| Expressions & Operators | 20 | 20 | 0 | 0 | **100%** |
| Statements | 10 | 10 | 0 | 0 | **100%** |
| Preprocessor (basic directives) | 17 | 17 | 0 | 0 | **100%** |
| Initialization | 6 | 6 | 0 | 0 | **100%** |
| Floating Point | 11 | 11 | 0 | 0 | **100%** |
| Code Generation | 9 | 9 | 0 | 0 | **100%** |
| C89 must-have gaps | 9 | 0 | 0 | 9 | **0%** |
| Preprocessor accuracy gaps | 8 | 0 | 0 | 8 | **0%** |
| Nice-to-have | 5 | 0 | 0 | 5 | **0%** |

**Implemented base features: ~98%** (113/115 items Done)
**Overall incl. C89 must-have gaps: ~83%** (113/136)
**Overall incl. preprocessor accuracy: ~78%** (113/144)
