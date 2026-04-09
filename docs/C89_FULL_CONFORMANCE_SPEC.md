# C89 Full Conformance Spec — Gap Analysis

Last updated: 2026-04-08

This document systematically enumerates **every C89 (ISO/IEC 9899:1990) feature**
organized by standard section, and records whether AuraCompiler implements it.

Methodology: each item was verified against the actual source code in `pycc/`,
not documentation claims.

Legend:
- ✅ = implemented + tested
- ⚠️ = partial (subset works, known limitations)
- ❌ = not implemented
- N/A = not applicable or implementation-defined (no action needed)

---

## §5.1 Translation Phases

| # | Phase | Status | Notes |
|---|-------|--------|-------|
| 1 | Trigraph replacement | ✅ | `preprocessor.py` `_replace_trigraphs()` |
| 2 | Line splicing (backslash-newline) | ✅ | `preprocessor.py` `_logical_lines()` |
| 3 | Tokenization into preprocessing tokens | ⚠️ | Regex-based, not full pp-token grammar |
| 4 | Preprocessing (macro expansion, includes, conditionals) | ⚠️ | Broad subset; see §6.8 below |
| 5 | Character set mapping | N/A | Assumes ASCII/UTF-8 host = execution |
| 6 | Adjacent string literal concatenation | ✅ | Parser handles at parse time |
| 7 | Semantic analysis + translation | ✅ | Full pipeline |
| 8 | Linking | ✅ | Via system `ld` |

---

## §6.1 Lexical Elements

| Feature | Status | Notes |
|---------|--------|-------|
| Keywords (all 32 C89 keywords) | ✅ | Lexer recognizes all |
| Identifiers | ✅ | |
| Integer constants (dec/oct/hex + U/L suffixes) | ✅ | |
| Floating constants (decimal + exponent + f/l suffix) | ✅ | `l`/`L` suffix parsed but `long double` not codegen'd |
| Character constants (incl. escape sequences) | ✅ | `\a \b \f \n \r \t \v \\ \' \" \? \0 \x \ooo` |
| Wide character constants `L'x'` | ✅ | Treated as `int` |
| String literals | ✅ | |
| Wide string literals `L"..."` | ✅ | Lexer handles L prefix |
| Operators and punctuators | ✅ | All C89 operators |
| Header names `<...>` and `"..."` | ✅ | |
| Preprocessing numbers | ⚠️ | Basic pp-number; not full grammar |
| Comments `/* */` | ✅ | |

---

## §6.2 Conversions

| Feature | Status | Notes |
|---------|--------|-------|
| Integer promotions | ✅ | `types.py` `integer_promote()` |
| Signed/unsigned integer conversions | ✅ | |
| Floating ↔ integer conversions | ✅ | SSE cvt instructions |
| Float ↔ double conversions | ✅ | cvtss2sd / cvtsd2ss |
| Long double conversions | ❌ | No x87 support |
| Pointer conversions (void*, null, qualified) | ✅ | |
| Pointer ↔ integer conversions (explicit cast) | ✅ | |
| Usual arithmetic conversions | ✅ | `types.py` `usual_arithmetic_conversions()` |
| Default argument promotions | ✅ | `semantics.py` `_apply_default_argument_promotions()` |

---

## §6.3 Expressions

| Feature | Status | Notes |
|---------|--------|-------|
| Primary: identifier, constant, string-literal, `(expr)` | ✅ | |
| Postfix: `[]`, `()`, `.`, `->`, `++`, `--` | ✅ | |
| Unary: `++`, `--`, `&`, `*`, `+`, `-`, `~`, `!`, `sizeof` | ✅ | |
| Cast expressions `(type-name)expr` | ✅ | |
| Multiplicative `* / %` | ✅ | |
| Additive `+ -` (incl. pointer arithmetic) | ✅ | |
| Shift `<< >>` | ✅ | |
| Relational `< > <= >=` | ✅ | |
| Equality `== !=` | ✅ | |
| Bitwise `& ^ \|` | ✅ | |
| Logical `&& \|\|` (short-circuit) | ✅ | |
| Conditional `?:` | ✅ | |
| Assignment `= += -= *= /= %= <<= >>= &= ^= \|=` | ✅ | |
| Comma operator | ✅ | |
| Constant expressions (ICE) | ✅ | Used in enum, case, array sizes, bitfields |

---

## §6.4 Declarations

| Feature | Status | Notes |
|---------|--------|-------|
| Storage-class: `auto` | ✅ | |
| Storage-class: `register` | ✅ | Hint only; `&` rejected |
| Storage-class: `static` (file scope) | ✅ | Internal linkage |
| Storage-class: `static` (block scope) | ✅ | Lowered to global with constant init |
| Storage-class: `extern` | ✅ | |
| Type specifiers: `void char short int long float double` | ✅ | |
| Type specifiers: `signed unsigned` | ✅ | |
| Type specifiers: `long double` | ❌ | Parsed but no IR/codegen |
| Type specifiers: `struct` / `union` | ✅ | |
| Type specifiers: `enum` | ✅ | |
| Type specifiers: `typedef` name | ✅ | |
| Type qualifiers: `const` | ✅ | Enforced in semantics |
| Type qualifiers: `volatile` | ⚠️ | Parsed; codegen does not honor |
| Declarators: simple, pointer, array, function | ✅ | |
| Declarators: complex nested (e.g. `int (*(*fp)(int))[10]`) | ⚠️ | Common cases work; extreme nesting may fail |
| Abstract declarators (in casts, sizeof) | ✅ | |
| `typedef` declarations | ✅ | |
| Initialization: scalar | ✅ | |
| Initialization: aggregate (brace-enclosed) | ✅ | |
| Initialization: designated `.member =` / `[index] =` | ❌ | AST node defined; parser/IR not implemented |
| Initialization: string literal for `char[]` | ✅ | |
| Initialization: nested struct/array | ✅ | Incl. brace elision |

---

## §6.5 Types

| Feature | Status | Notes |
|---------|--------|-------|
| Object types | ✅ | |
| Function types | ✅ | |
| Incomplete types (forward-declared struct/union) | ⚠️ | sizeof rejected; pointer-to-incomplete works; limited checking |
| Compatible types (same TU) | ⚠️ | Basic function redecl compat; no full composite type algorithm |
| Compatible types (across TUs) | ⚠️ | Driver checks return type + param count; not full |
| Composite types | ❌ | No composite type construction |

---

## §6.6 Statements

| Feature | Status | Notes |
|---------|--------|-------|
| Labeled statement (identifier `:`) | ✅ | |
| `case` constant-expression `:` | ✅ | ICE enforced |
| `default :` | ✅ | |
| Compound statement `{ }` | ✅ | Nested scopes |
| Expression statement | ✅ | |
| `if` / `else` | ✅ | |
| `switch` | ✅ | Incl. fallthrough, duplicate case/default rejection |
| `while` | ✅ | |
| `do` ... `while` | ✅ | |
| `for` | ✅ | |
| `goto` | ✅ | |
| `continue` | ✅ | |
| `break` | ✅ | |
| `return` (with/without value) | ✅ | |
| Null statement `;` | ✅ | |

---

## §6.7 External Definitions

| Feature | Status | Notes |
|---------|--------|-------|
| Function definitions (prototype style) | ✅ | |
| Function definitions (K&R old-style) | ✅ | |
| External object definitions | ✅ | |
| Tentative definitions | ✅ | `.comm` emission |
| Linkage: external | ✅ | |
| Linkage: internal (`static`) | ✅ | |
| Linkage: none (block scope) | ✅ | |
| Implicit `int` return type (C89) | ⚠️ | Implicit function decl allowed; implicit int for variables rejected |
| One-definition rule (across TUs) | ⚠️ | Driver checks for multiple strong defs; not exhaustive |

---

## §6.8 Preprocessing Directives

| Feature | Status | Notes |
|---------|--------|-------|
| `#include "..."` | ✅ | |
| `#include <...>` | ✅ | System path probing via gcc |
| `#include` with macro-expanded operand | ⚠️ | Subset: expands to header-name |
| `#define` object-like | ✅ | |
| `#define` function-like | ✅ | |
| `#define` variadic `...` / `__VA_ARGS__` | ✅ | Incl. GNU `, ##__VA_ARGS__` |
| `#undef` | ✅ | |
| `#if` / `#elif` / `#else` / `#endif` | ✅ | Full expression eval |
| `#ifdef` / `#ifndef` | ✅ | |
| `defined` operator | ✅ | |
| `#line` | ✅ | |
| `#error` | ✅ | |
| `#pragma` | ✅ | Unknown pragmas ignored; `once` supported |
| Null directive `#` | ✅ | |
| `#` stringize operator | ⚠️ | Basic escaping; tabs/newlines/trigraphs incomplete |
| `##` token paste operator | ⚠️ | Basic paste + rescan; edge cases incomplete |
| Macro rescanning / hide-set | ⚠️ | Works for common cases; not standards-accurate algorithm |
| Predefined macros `__LINE__ __FILE__ __DATE__ __TIME__ __STDC__` | ✅ | |

---

## §6.3.2.3 Structure and Union Members (by-value operations)

| Feature | Status | Notes |
|---------|--------|-------|
| `struct`/`union` member access `.` | ✅ | |
| `struct`/`union` member access `->` | ✅ | |
| `struct` by-value assignment `a = b` | ❌ | No memcpy-style copy codegen |
| `struct` by-value parameter passing | ❌ | No SysV struct-in-regs/stack ABI |
| `struct` by-value return | ❌ | No hidden-pointer / rax:rdx return |
| `union` by-value assignment | ❌ | Same as struct |
| `union` by-value parameter passing | ❌ | Same as struct |
| `union` by-value return | ❌ | Same as struct |
| Bit-field member access | ✅ | Read/write codegen |
| Bit-field layout | ✅ | |

---

## §7 Library (stdarg.h — required for variadic functions)

| Feature | Status | Notes |
|---------|--------|-------|
| `va_list` type | ✅ | `__builtin_va_list` modeled |
| `va_start` | ✅ | `__builtin_va_start` codegen (SysV AMD64) |
| `va_end` | ✅ | `__builtin_va_end` codegen |
| `va_arg` | ❌ | Not implemented; cannot extract args in user variadic functions |
| Pass `va_list` to libc (e.g. `vsnprintf`) | ✅ | |

---

## Summary: All ❌ Items (must implement for C89 conformance)

| # | Feature | C89 Section | Effort | Impact |
|---|---------|-------------|--------|--------|
| 1 | `struct`/`union` by-value assignment | §6.3.16.1 | Medium | High — very common in real C code |
| 2 | `struct`/`union` by-value parameter passing | §6.7.1 | Medium | High — required for any struct-passing API |
| 3 | `struct`/`union` by-value return | §6.6.6.4 | Medium | High — required for functions returning structs |
| 4 | `va_arg` macro/builtin | §7.8.1.2 | Medium | High — required for user-defined variadic functions |
| 5 | `long double` type (full) | §6.1.2.5 | Medium | Low — rarely used in practice |
| 6 | Designated initializers | §6.5.7 | Medium | Medium — common in real code |
| 7 | Composite type construction | §6.1.2.6 | Low | Low — affects multi-TU type merging |

## Summary: All ⚠️ Items (partial, should improve)

| # | Feature | C89 Section | Effort | Impact |
|---|---------|-------------|--------|--------|
| 1 | `volatile` codegen semantics | §6.5.3 | Low | Medium — affects hardware/signal code |
| 2 | Preprocessing token grammar (full) | §6.1 | High | Medium — affects complex macro usage |
| 3 | Macro expansion algorithm (standards-accurate) | §6.8.3 | High | Medium — affects complex macro patterns |
| 4 | `#` stringize full escaping | §6.8.3.2 | Low | Low |
| 5 | `##` token paste full legality | §6.8.3.3 | Low | Low |
| 6 | Compatible type algorithm (full) | §6.1.2.6 | Medium | Medium — affects multi-TU correctness |
| 7 | Incomplete type checking (full) | §6.5.2.3 | Low | Low |
| 8 | Complex nested declarators | §6.5.4 | Low | Low — extreme cases only |
| 9 | Function pointer param type checking | §6.5.4.3 | Low | Low |
| 10 | Implicit `int` return type | §6.7.1 | Low | Low — C89 legacy feature |
| 11 | `#include` macro-expanded operand (full) | §6.8.2 | Low | Low |

---

## Quantified Totals

Counted from all tables above (deduplicated):

| Status | Count |
|--------|-------|
| ✅ Fully implemented | **104** |
| ⚠️ Partial | **14** |
| ❌ Not implemented | **7** |
| N/A | **1** |
| **Total C89 features** | **126** |

**Feature completeness: 104/125 = 83.2%**
**Including partial: 118/125 = 94.4%**

## Recommended Implementation Order

Priority based on impact to real-world C89 code compilation:

### Phase 1 — High impact (unblocks most real C89 programs)
1. `struct`/`union` by-value assignment (`a = b` via memcpy)
2. `struct`/`union` by-value parameter passing (SysV ABI classification)
3. `struct`/`union` by-value return (SysV ABI hidden pointer / rax:rdx)
4. `va_arg` builtin (SysV AMD64 register save area traversal)

### Phase 2 — Medium impact
5. Designated initializers (`.member = val`, `[index] = val`)
6. `volatile` codegen (prevent reordering/elimination)
7. Function pointer full type compatibility checking

### Phase 3 — Standards accuracy
8. Preprocessor: token-based macro expansion engine
9. Compatible/composite type algorithm
10. `long double` x87 codegen

### Phase 4 — Polish
11. Full `#`/`##` operator edge cases
12. Complex nested declarator edge cases
13. Incomplete type checking improvements
