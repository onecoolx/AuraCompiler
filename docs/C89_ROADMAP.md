# C89 Implementation Roadmap

Last updated: 2026-04-07

## Current Status

- `pytest -q`: **916 passed**
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
| Wide character L'x' | **TODO** | Parser doesn't handle L prefix |
| Adjacent string concatenation | **TODO** | "ab" "cd" → "abcd" |
| Trigraphs | **TODO** | Obscure, low priority |

### Declarations

| Feature | Status | Notes |
|---------|--------|-------|
| Single declarator | **DONE** | `int x;` `int x = 1;` |
| Multiple declarators per statement | **TODO** | `int a, b;` `int a=1, b=2;` |
| Function prototypes + definitions | **DONE** | |
| K&R function definitions | **DONE** | `int f(a,b) int a; int b; {...}` |
| `extern` declarations | **DONE** | |
| `static` global | **DONE** | |
| `static` local | **PARTIAL** | Works with separate init, not `static int x=0;x++;` |
| `register` storage class | **DONE** | (treated as hint, address-of rejected) |
| `auto` storage class | **DONE** | |
| Bit-fields | **TODO** | `struct { int x:4; }` |
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
| `typedef struct { } T;` (anonymous) | **TODO** | Semantics doesn't track anonymous typedef'd structs |
| `const` qualifier | **DONE** | assignment rejection, pointer compat |
| `volatile` qualifier | **DONE** | (parsed, no special codegen) |
| Integer promotion | **DONE** | CType-based in types.py |
| Usual arithmetic conversions | **DONE** | CType-based in types.py |
| Pointer ↔ void* implicit conversion | **DONE** | |
| Incompatible pointer rejection | **DONE** | |
| Function pointer compatibility | **DONE** | arity check |
| `sizeof(type)` | **PARTIAL** | Works for builtins/pointers, **TODO** for `sizeof(struct S)` |
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
| Pre-increment `++x` | **TODO** | Parser doesn't handle |
| Post-increment `x++` | **TODO** | Parser doesn't handle |
| Pre-decrement `--x` | **TODO** | Parser doesn't handle |
| Post-decrement `x--` | **TODO** | Parser doesn't handle |
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
| Float/double global initializer | **TODO** | IR only supports int/char/string globals |

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
| Float global variables | **TODO** | No float global initializer support |
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

## Missing Features Summary (9 items)

Grouped by estimated effort. Full spec: `.kiro/specs/c89-remaining/`

### Small (1-2 hours each)

1. **`++` / `--` operators** — Parser needs to handle INCREMENT/DECREMENT tokens. Blocks `for(;;i++)`.
2. **Multiple declarators** — `int a, b;` and `int a=1, b=2;` — Parser needs comma-separated declarator list.
3. **Adjacent string literal concatenation** — `"ab" "cd"` → `"abcd"`.
4. **`sizeof(struct S)`** — Semantics needs to look up struct layout for sizeof on aggregate types.
5. **Float global initializers** — IR needs to emit float constants in .data section.
6. **`typedef struct {} T;`** — Semantics needs to track anonymous struct types through typedef.

### Medium (2-4 hours each)

7. **Bit-fields** — Parser, semantics (layout), IR, and codegen all need changes.
8. **Wide character `L'x'` / `L"str"`** — Lexer needs to handle L prefix.

### Low Priority

9. **Trigraphs** — `??=` → `#`, etc. Almost never used in practice.

## Estimated Remaining Work

| Category | Items | Est. Hours |
|----------|-------|------------|
| Small fixes (1-6) | 6 | 6-12 |
| Medium features (7-8) | 2 | 4-8 |
| Low priority (9) | 1 | 1 |
| **Total** | **9** | **~11-21** |

The compiler handles **~90%** of C89 language features. The biggest practical gap is `++`/`--` operators (item 1), which blocks idiomatic C loop patterns like `for(i=0;i<n;i++)`.
