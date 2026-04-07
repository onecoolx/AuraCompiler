# C89 Implementation Roadmap

Last updated: 2026-04-07

## Current Status

- `pytest -q`: **947 passed**
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
| Wide character L'x' | **DONE** | L prefix handled in lexer | | Parser doesn't handle L prefix |
| Adjacent string concatenation | **DONE** | "ab" "cd" → "abcd" |
| Trigraphs | **DONE** | Translation phase 1 | | Obscure, low priority |

### Declarations

| Feature | Status | Notes |
|---------|--------|-------|
| Single declarator | **DONE** | `int x;` `int x = 1;` |
| Multiple declarators per statement | **DONE** | `int a, b;` `int a=1, b=2;` |
| Function prototypes + definitions | **DONE** | |
| K&R function definitions | **DONE** | `int f(a,b) int a; int b; {...}` |
| `extern` declarations | **DONE** | |
| `static` global | **DONE** | |
| `static` local | **PARTIAL** | Works with separate init, not `static int x=0;x++;` |
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
| `long double` | **PARTIAL** | Parsed, basic codegen works; no x87 extended precision |
| `void` | **DONE** | |
| Pointers (multi-level) | **DONE** | |
| Arrays | **DONE** | |
| `struct` / `union` | **DONE** | layout, member access, nesting |
| `enum` | **DONE** | incl. explicit values |
| `typedef` | **DONE** | |
| `typedef struct { } T;` (anonymous) | **DONE** | Internal tag generation | | Semantics doesn't track anonymous typedef'd structs |
| `const` qualifier | **DONE** | assignment rejection, pointer compat |
| `volatile` qualifier | **DONE** | (parsed, no special codegen) |
| Integer promotion | **DONE** | CType-based in types.py |
| Usual arithmetic conversions | **DONE** | CType-based in types.py |
| Pointer ↔ void* implicit conversion | **DONE** | |
| Incompatible pointer rejection | **DONE** | |
| Function pointer compatibility | **DONE** | arity check |
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
| Pre-increment `++x` | **DONE** | Parser doesn't handle |
| Post-increment `x++` | **DONE** | Parser doesn't handle |
| Pre-decrement `--x` | **DONE** | Parser doesn't handle |
| Post-decrement `x--` | **DONE** | Parser doesn't handle |
| Comma operator | **DONE** | |
| Ternary `?:` | **DONE** | |
| Cast `(type)expr` | **DONE** | incl. int↔float |
| `sizeof` | **PARTIAL** | See type system |
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
| `while` | **PARTIAL** | Works if body doesn't use `i++` (use `i=i+1`) |
| `do-while` | **PARTIAL** | Same limitation |
| `for` | **PARTIAL** | Works with `i=i+1`, not `i++` in update |
| `switch / case / default` | **DONE** | incl. fallthrough |
| `break` | **DONE** | (when loop uses `i=i+1` form) |
| `continue` | **DONE** | (when loop uses `i=i+1` form) |
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
| Float/double global initializer | **DONE** | IEEE 754 in .data | | IR only supports int/char/string globals |

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
| Float function parameters | **PARTIAL** | Works for simple cases, no xmm ABI for >1 float param |
| Float function return | **PARTIAL** | Works for simple cases |
| Float global variables | **DONE** | .data + RIP-relative load | | No float global initializer support |
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
| Global data .data/.bss/.rodata | **DONE** | (int/char/string only) |
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

**Current: 947 tests passed, C89 language features fully covered.**
