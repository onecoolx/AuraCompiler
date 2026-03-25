# AuraCompiler (pycc): Practical C89 Compiler - Project Summary

Last updated: 2026-03-18

## Executive Summary

AuraCompiler is a practical C89/ANSI C compiler in Python targeting x86-64 SysV Linux. It follows a classic frontend/middle/back pipeline and is driven by an end-to-end pytest suite. This document provides:

1. **Detailed Architecture Design** - How each component works
2. **Complete Development Plan** - Phased implementation roadmap
3. **Comprehensive Testing Strategy** - All test cases and scenarios
4. **Project Structure** - File organization and dependencies

---

## Part 1: Project Structure & Setup

### Directory Layout

```
pycc/
├── README.md                      # Project overview
├── requirements.txt              # Python dependencies (pytest, coverage)
├── docs/
│   ├── ARCHITECTURE.md          # Detailed architecture (included)
│   ├── DEVELOPMENT_PLAN.md      # Full development roadmap (included)
│   └── PROJECT_SUMMARY.md       # This file
├── pycc/                        # Main compiler package
│   ├── __init__.py              # Package initialization
│   ├── lexer.py                 # Lexical analysis (COMPLETE ✓)
│   ├── parser.py                # Syntax analysis (IMPLEMENTED ✓; still expanding)
│   ├── ast_nodes.py             # AST definitions (COMPLETE ✓)
│   ├── semantics.py             # Semantic analysis (IMPLEMENTED ✓; conservative)
│   ├── ir.py                    # Intermediate representation (IMPLEMENTED ✓)
│   ├── optimizer.py             # Optimization passes (PARTIAL ✓)
│   ├── codegen.py               # Code generation (IMPLEMENTED ✓)
│   └── compiler.py              # Main compiler driver (IMPLEMENTED ✓)
├── tests/
│   ├── __init__.py
│   ├── test_lexer.py            # Lexer unit tests (COMPLETE ✓)
│   ├── test_parser.py           # Parser unit tests (legacy placeholder; see many feature tests instead)
│   ├── test_semantics.py        # Semantic tests (legacy placeholder; see many feature tests instead)
│   ├── test_codegen.py          # Code gen tests (legacy placeholder; see many feature tests instead)
│   ├── test_integration.py      # Integration tests (COMPLETE ✓)
│   └── testcases/               # C source test files (TODO)
├── examples/
│   ├── hello.c                  # Hello world example
│   ├── factorial.c              # Recursive factorial
│   ├── fibonacci.c              # Fibonacci sequence
│   └── arrays.c                 # Array operations
```

### Current Implementation Status (reality)

**Working end-to-end:** Lexer → Parser → Semantics → IR → Codegen → `as`/`ld`.

**Test status:** `pytest -q` is the source of truth. Current tree: **747 passed**.

### Recent changes

- Fixed libc varargs crash cases by ensuring SysV x86-64 call-site stack alignment (16-byte aligned at each `call`).
- Fixed local-scope `extern` function prototypes used with calls (e.g. `extern int printf(const char*, ...);` inside a function) so they resolve as direct symbol calls.
- Added regression test: `tests/test_variadic_printf_local_extern_proto.py`.
- Fixed a for-loop infinite-loop bug caused by stack slot aliasing between user locals (`@i/@j`) and IR temporaries (`%t*`). Root cause was an inconsistent frame-offset scheme when reserving a fixed spill area; compare results were accidentally stored into the loop variable slot.
- Implemented a consistent frame layout rule in `pycc/codegen.py`: declared locals occupy the top of the frame; temps/spills use a reserved spill region below locals; any late-discovered locals are allocated below the spill region. This prevents overlaps and stabilizes control-flow correctness.
- Preprocessor: improved `#if` expression compatibility for system headers by accepting integer literal suffixes (e.g. `201710L`) and tolerating function-like macro calls in `#if` (treated as 0). Also enhanced `#if`/`#elif` error diagnostics with directive file:line.
- Preprocessor: macro-expanded `#include` operands (subset) and additional token-boundary / termination hardening for macro expansion (pp-number boundaries; self-referential termination subsets).

- Variadic ABI (SysV AMD64): fixed glibc-compatible `va_list` handling so a `va_list` can be passed to libc `v*` entrypoints (e.g. `vsnprintf`). Documented in `docs/ARCHITECTURE.md` (2.6.1) and covered by regression tests.

- Multi-translation-unit (multi-TU) behavior improved (tentative definitions as `.comm`, `extern` without storage in TU, cross-TU conflicts checked in driver tests).
- Multi-dimensional arrays (2D) groundwork added:
    - Parser records `Declaration.array_dims` (outer→inner).
    - 2D array decay to pointer-to-row uses IR metadata (`ptr_step_bytes`) and codegen scaling.
    - `sizeof(local 2D array)` computes total bytes.
    - Nested `a[i][j]` is implemented and covered by tests.

**Implemented highlights (see tests/):**
- Globals + initializers (including global `char*` string literal pointer init)
- `typedef`
- `struct`/`union` basic layout + member access (`.` / `->`)
- Arrays (int) and pointer/array indexing for common cases
- Storage class: top-level `static`/`extern` (minimal)
- `switch/case/default` (compare-chain lowering + fallthrough)
- `sizeof` (minimal subset)
- C-style cast `(type)expr` (minimal subset)
- `enum` definitions + enumerator constants
- `goto`/labels

**Known gaps (updated):**
- Preprocessor is implemented (broad subset) but still incomplete. See `docs/PREPROCESSOR_C89_CHECKLIST.md`.
- No floating point (`float`/`double`) codegen/type rules
- C89 integer promotions / usual arithmetic conversions not fully modeled
- Full declarator/type grammar coverage is incomplete (many edge cases)
- Initializers are still incomplete, but aggregate initializers (including nested local structs) are now covered by tests; remaining gaps are mostly edge-cases (designators, mixed scalar/aggregate corner cases, more global aggregate forms).
- Translation-unit / multi-file model is still incomplete in general, but a practical multi-TU workflow is implemented and tested.
- Diagnostics and conformance testing vs `gcc -std=c89` not comprehensive yet

---

## Part 2.5: C89 Conformance Tracker (living)

This section is the **source of truth** for what AuraCompiler supports today and what remains.

Legend: **DONE** = implemented + tested; **PARTIAL** = implemented subset + tested; **TODO** = not implemented.

### Frontend: Lexing / Preprocessing

- **DONE**: Tokens for C operators, delimiters, identifiers, integer/char/string literals, comments.
- **PARTIAL**: Keywords set includes many non-C89 keywords (lexer accepts them).
- **PARTIAL**: Preprocessor: `#include`, `#define` (object/function-like), `#if/#ifdef/#ifndef/#else/#elif/#endif`, `#line`, `#error`, `#warning`, `#pragma once` (subset). Missing full macro expansion semantics; macro-expanded includes are supported as a subset (see `docs/PREPROCESSOR_C89_CHECKLIST.md`).

### Declarations / Types

- **DONE**: `int`, `char`, pointers, arrays (common cases), function prototypes + definitions.
- **DONE**: `typedef`.
- **DONE**: `struct`/`union` basic layout + member access (`.`/`->`).
- **DONE**: `enum` definitions + enumerator constants.
- **PARTIAL**: Storage class (`static`/`extern`) behavior and linkage model.
- **TODO**: Full declarator grammar (pointer qualifiers, complex nested declarators, old-style K&R function definitions if desired).
- **TODO**: `const`/`volatile` qualifiers semantics.
- **TODO**: Signed/unsigned variants, `short`/`long` widths and conversions.

### Expressions / Semantics

- **DONE**: Integer arithmetic/bitwise/compare, assignment, calls, `?:`, `sizeof`, C-style cast.
- **DONE**: `&&` / `||` short-circuit.
- **PARTIAL**: Type checking (best-effort), implicit function declarations (C89-style) for external calls.
- **TODO**: Integer promotions + usual arithmetic conversions.
- **PARTIAL**: Pointer conversions and pointer operations (best-effort, tested):
    - **DONE**: Pointer +/- integer scaling by pointee size.
    - **DONE**: Pointer - pointer yields element distance (not bytes).
    - **DONE**: Unary dereference `*(p + i)` (read) via IR `load`.
    - **DONE**: Store-through-pointer `*p = v` (write) via IR `store`.
    - **DONE**: Narrow pointee loads are correctly extended:
        - `unsigned char*` / `unsigned short*` load: **zero-extend**.
        - `char*` / `signed char*` / `short*` load: **sign-extend**.
    - **DONE**: Pointer comparisons `== != < <= > >=` for common cases.
    - **DONE (conservative)**: Reject pointer + pointer.
    - **DONE (conservative)**: Reject `void*` subtraction.
    - **DONE (conservative)**: Reject pointer subtraction for different base types (e.g. `int* - char*`).
    - **TODO**: More complete pointer conversions/qualification rules and diagnostics.

- **DONE**: Backend correctness fixes triggered by narrow pointer tests:
    - Pointers are always treated as 8-byte values in local/temp load/store selection (avoid truncation from string-prefix type matches like `"unsigned char*"`).
    - Variadic calls (e.g. `printf`) emit the required SysV AMD64 ABI setup (`%al = 0` when passing no vector args).

### Statements / Control flow

- **DONE**: `if/else`, `for`, `while`, `do/while`, `switch/case/default`, `break/continue`, `goto`/labels.

### Data / Initialization / Linking

- **PARTIAL**: String literals in `.rodata` and basic global initializers.
- **TODO**: Full initializer support (scalars + aggregates), including nested aggregate initialization.
- **TODO**: `.bss/.data` emission for more global/static objects with correct alignment/relocations.
- **PARTIAL**: Multi-translation-unit compilation model (multi-file driver + link orchestration in tests); `extern` across units is still limited.

### Testing / Compliance

- **DONE**: pytest suite covering many implemented features.
- **TODO**: Systematic conformance suite for C89 (feature matrix + targeted tests) and behavior comparison with `gcc -std=c89`.

---

## Part 2.6: Design Notes & Long-Term Memory (living)

For durable project context (design invariants + workflow/commit rules), see:
`docs/LONG_TERM_MEMORY.md`.

This section captures **how we are extending C89 coverage** in a way that is robust to context loss.

### 2.6.1 Development workflow (contract)

- Drive changes by **pytest tests** first.
- Keep the suite green; use **small commits**.
- When a new test reveals a missing traversal/typing edge, prefer:
    1) fix traversal in `pycc/semantics.py`,
    2) fix lowering in `pycc/ir.py`,
    3) fix emission in `pycc/codegen.py`,
    4) then add/extend tests.

### 2.6.2 Current pointer operation design (MVP rules)

The compiler is intentionally "stringly-typed" in the IR/codegen boundary.
We keep enough type info to choose element widths and scale pointer arithmetic.

#### Key IR ops

- `load`: `result = *(operand1)`
- `store`: `*(operand1) = result`

Both are implemented in `pycc/codegen.py` with **best-effort width selection** based on the pointer's pointee type.

#### Pointer arithmetic lowering (IR)

- For `ptr +/- int`: scale the integer by pointee size (e.g. `int*` scales by 4).
- For `ptr - ptr`: compute byte difference and divide by pointee size to return element count.
- Propagate pointer type through temporaries so later `load/store/load_index` can pick correct widths.

#### Conservative semantic restrictions (Semantics)

- Reject `pointer + pointer`.
- Reject `void* - void*` and generally `void*` subtraction.
- Reject `T* - U*` when base types differ (e.g. `int* - char*`).

### 2.6.3 Recent progress snapshot (as of 2026-02)

Pointer feature work added end-to-end support and tests:

- Semantics:
    - Traverse `Cast` expressions so nested checks run.
    - Conservative pointer subtraction restrictions (base mismatch; `void*`).
- IR:
    - Add unary dereference lowering (`*p`) via `load`.
    - Add store-through-pointer lowering (`*p = v`) via `store`.
    - Pointer scaling for `+/-` and pointer-diff scaling for `-`.
- Codegen:
    - Emit `load` and `store` with width-aware `mov*` sequences.

Representative tests added:

- `tests/test_unary_deref_pointer_arith.py` (`*(p+2)` read)
- `tests/test_store_through_pointer.py` (`*p = v` write)
- `tests/test_pointer_comparisons_more.py` (more `== != < <= > >=` coverage)

### 2.6.4 Next steps (planned)

1) Add **negative/diagnostic tests** for pointer compares in invalid contexts (e.g. pointer vs integer without cast), and tighten `pycc/semantics.py` accordingly. (DONE for relational compares)
2) Expand pointer loads/stores across types (`short`, `unsigned`, structs) once type strings are reliable.
3) Continue C89 conformance expansion via targeted tests with small green commits.

#### Recent tightening

- Relational pointer comparisons now reject:
    - pointer vs non-pointer comparisons (e.g. `p < 1`)
    - `void*` relational comparisons (e.g. `p < q` where either is `void*`)
    - while allowing **ptrdiff-like** integer expressions (e.g. `(q - p) < 3`) to be compared against integers.

- Equality pointer comparisons now reject:
    - pointer vs non-pointer comparisons (e.g. `p == 1`)
    - while allowing comparisons to null pointer constant subset (currently: literal `0` / casts of `0`, including pointer casts like `(int*)0`).

---

## Part 2: Detailed Architecture

### 2.1 Compilation Pipeline

```
Source Code (.c)
     ↓
[LEXER] ─────────────────→ Tokens
     ↓
[PARSER] ────────────────→ Abstract Syntax Tree (AST)
     ↓
[SEMANTIC ANALYZER] ─────→ Annotated AST + Symbol Table
     ↓
[IR GENERATOR] ──────────→ 3-Address Code (TAC)
     ↓
[OPTIMIZER] ─────────────→ Optimized IR
     ↓
[CODE GENERATOR] ────────→ x86-64 Assembly (.s)
     ↓
[ASSEMBLER] ─────────────→ Object Code (.o)
     ↓
[LINKER] ────────────────→ Executable
```

### 2.2 Module Details

#### **Lexer (lexer.py) - COMPLETE**

**Purpose**: Convert source code into tokens

**Features Implemented**:
- Token recognition:
  - C99 Keywords (64 keywords)
  - Identifiers (alphanumeric + underscore)
  - Numbers (decimal, hex, octal, float with exponent)
  - String literals with escape sequences
  - Character literals
  - All operators (arithmetic, logical, bitwise, comparison, assignment)
  - Delimiters (parentheses, braces, brackets, etc.)
  - Comments (single-line // and multi-line /* */)

**Key Classes**:
```python
class Token:
    type: TokenType      # Token classification
    value: str          # Token text
    line: int           # Source line number
    column: int         # Column number

class Lexer:
    tokenize()          # Main entry point
    current_char()      # Peek current character
    advance()           # Consume character
    read_string()       # Parse string literal
    read_number()       # Parse numeric literal
    read_identifier()   # Parse identifier/keyword
```

**Token Types** (31 types):
- Literals: NUMBER, CHAR, STRING
- Identifiers: IDENTIFIER, KEYWORD
- Operators: PLUS, MINUS, STAR, SLASH, etc. (17 types)
- Delimiters: LPAREN, RPAREN, LBRACE, RBRACE, etc. (8 types)
- Special: EOF, NEWLINE

**Example Output**:
```
Input:  int x = 5;
Tokens: [
  Token(KEYWORD, 'int', 1:1),
  Token(IDENTIFIER, 'x', 1:5),
  Token(ASSIGN, '=', 1:7),
  Token(NUMBER, '5', 1:9),
  Token(SEMICOLON, ';', 1:10),
  Token(EOF, '', 1:11)
]
```

#### **AST Nodes (ast_nodes.py) - COMPLETE**

**Purpose**: Define structure for abstract syntax tree

**Node Hierarchy**:
```
ASTNode (base class, line/column)
├── Type System
│   ├── Type (base, pointer, const, volatile, restrict, signed/unsigned)
│   ├── ArrayType
│   ├── PointerType
│   └── FunctionType
├── Declarations (14 types)
│   ├── Declaration (variable/parameter)
│   ├── FunctionDecl
│   ├── StructDecl, UnionDecl
│   ├── TypedefDecl
│   └── EnumDecl
├── Statements (15 types)
│   ├── CompoundStmt, ExpressionStmt
│   ├── IfStmt, WhileStmt, DoWhileStmt, ForStmt
│   ├── SwitchStmt, CaseStmt, DefaultStmt
│   ├── BreakStmt, ContinueStmt
│   ├── ReturnStmt, GotoStmt, LabelStmt
│   └── DeclStmt
└── Expressions (20 types)
    ├── Identifier, IntLiteral, FloatLiteral, CharLiteral, StringLiteral
    ├── BinaryOp, UnaryOp, TernaryOp
    ├── Assignment, FunctionCall
    ├── ArrayAccess, MemberAccess, PointerMemberAccess
    ├── Cast, SizeOf, AlignOf
    ├── Initializer, Designator, CompoundLiteral
    └── Program (root)
```

**Type System Support**:
- Primitive types: void, char, short, int, long, float, double
- Type qualifiers: const, volatile, restrict, unsigned, signed
- Derived types: pointers (*), arrays ([]), functions (())
- Aggregate types: struct, union, enum

#### **Parser (parser.py) - IMPLEMENTED (subset; expanding)**

**Purpose**: Build AST from token stream

**Strategy**: Recursive descent with operator precedence climbing

**Remaining TODOs**:
1. Expression parser (14 precedence levels)
2. Statement parser (if, while, for, switch, etc.)
3. Declaration parser (variables, functions, structs, etc.)
4. Type specifier parser
5. Error recovery mechanisms

**Operator Precedence** (C99 standard):
```
Level 1:  Postfix: ++, --, (), [], ., ->
Level 2:  Unary: ++, --, +, -, !, ~, *, &, sizeof
Level 3:  Multiplicative: *, /, %
Level 4:  Additive: +, -
Level 5:  Shift: <<, >>
Level 6:  Relational: <, >, <=, >=
Level 7:  Equality: ==, !=
Level 8:  Bitwise AND: &
Level 9:  Bitwise XOR: ^
Level 10: Bitwise OR: |
Level 11: Logical AND: &&
Level 12: Logical OR: ||
Level 13: Conditional: ? :
Level 14: Assignment: =, +=, -=, etc.
Level 15: Comma: ,
```

#### **Symbol Table & Type System (semantics.py) - IMPLEMENTED (conservative)**

**Purpose**: Track symbols and enforce type rules

**Features (current)**:
- Multi-level scope management
- Symbol lookup with scope chain
- Type compatibility checking
- Type conversion rules
- Function signature validation
- struct/union member resolution

**Scope Levels**:
1. Global scope (file-level)
2. Function scope (parameter scope)
3. Block scope (nested {...})

#### **Intermediate Representation (ir.py) - IMPLEMENTED**

**Purpose**: Convert AST to 3-Address Code (TAC)

**IR Instruction Types**:
```python
class IRInstruction:
    op: str              # Operation type
    result: Optional[str]      # Destination
    operand1: Optional[str]    # First operand
    operand2: Optional[str]    # Second operand (for binary)
    label: Optional[str]       # Jump target
    args: Optional[List]       # Function arguments
```

**Instruction Categories**:
1. Binary operations: x = y + z
2. Unary operations: x = -y
3. Assignments: x = y
4. Function calls: x = call func(args)
5. Jumps: goto label
6. Conditional jumps: if x goto label
7. Labels: label:
8. Return: return x

**Example**:
```
Input AST:   int x = (a + b) * c;
Output IR:
  t0 = a + b
  t1 = t0 * c
  x = t1
```

#### **Optimizer (optimizer.py) - IMPLEMENTED (basic passes)**

**Purpose**: Improve IR code quality

**Note**: Current pass set is partial; see tests for coverage and behavior.

**Optimization Passes**:

1. **Constant Folding**
   - Evaluate constant expressions at compile-time
   - `2 + 3` → `5`
   - `10 > 5` → `1`

2. **Constant Propagation**
   - Replace variables with known constant values
   - `x = 5; y = x;` → `y = 5;`

3. **Dead Code Elimination**
   - Remove unused assignments
   - `x = 5;` (x never read) → remove

4. **Common Subexpression Elimination**
   - Identify and eliminate redundant computations
   - `a = b + c; d = b + c;` → `a = b + c; d = a;`

5. **Strength Reduction**
   - Replace expensive operations with cheaper ones
   - `x * 2` → `x << 1`
   - `x / 2` → `x >> 1`

6. **Loop Optimization**
   - Invariant code motion
   - Loop unrolling (limited)

#### **Code Generator (codegen.py) - IMPLEMENTED (x86-64 SysV; expanding)**

**Purpose**: Generate x86-64 assembly code

**Target**: System V AMD64 ABI (Linux)

**Features**:
- x86-64 instruction selection
- Register allocation (greedy)
- Stack frame management
- Function prologue/epilogue
- Calling convention implementation

**Calling Convention** (System V AMD64):
```
First 6 integer arguments:  rdi, rsi, rdx, rcx, r8, r9
Return value:              rax (or rdx:rax for 128-bit)
Callee-saved registers:    rbx, rbp, r12-r15
Caller-saved registers:    rax, rcx, rdx, rsi, rdi, r8-r11
Stack alignment:           16-byte before call instruction
```

**Assembly Sections**:
```asm
.section .data           ; Initialized global data
.section .bss            ; Uninitialized global data  
.section .rodata         ; Read-only data (strings, constants)
.section .text           ; Code
```

---

## Part 3: Development Phases

### Phase 1: Lexer & AST (COMPLETED)
**Status**: ✓ DONE
- Lexer implementation: Complete
- AST nodes: Complete
- Lexer tests: 40+ test cases

### Phase 2: Parser (IMPLEMENTED; expanding)
**Estimated Duration**: 1 week
**Status**: ✓ IMPLEMENTED (subset; expanding)
**Remaining tasks**:
- [ ] Recursive descent parser skeleton
- [ ] Expression parser with precedence
- [ ] Statement parser
- [ ] Declaration parser
- [ ] Error recovery
- [ ] Parser unit tests (50+ cases)

**Example Parser Usage**:
```python
lexer = Lexer("int main() { return 0; }")
tokens = lexer.tokenize()
parser = Parser(tokens)
ast = parser.parse()

# ast is now: Program([
#   FunctionDecl(
#     name='main',
#     return_type=Type('int'),
#     parameters=[],
#     body=CompoundStmt([
#       ReturnStmt(IntLiteral(0))
#     ])
#   )
# ])
```

### Phase 3: Semantic Analysis
**Estimated Duration**: 1 week
**Status**: ✓ IMPLEMENTED (conservative)
**Remaining tasks**:
- [ ] Symbol table implementation
- [ ] Type system implementation
- [ ] Type checking
- [ ] Scope management
- [ ] Error detection
- [ ] Semantic tests (40+ cases)

### Phase 4: IR Generation & Optimization
**Estimated Duration**: 1 week
**Status**: ✓ IMPLEMENTED (basic)
**Remaining tasks**:
- [ ] IR instruction definition
- [ ] AST to IR conversion
- [ ] Optimization passes
- [ ] IR tests (30+ cases)

### Phase 5: Code Generation
**Estimated Duration**: 2 weeks
**Status**: ✓ IMPLEMENTED (x86-64 SysV)
**Remaining tasks**:
- [ ] x86-64 instruction selection
- [ ] Register allocation
- [ ] Function prologue/epilogue
- [ ] Calling convention
- [ ] Code generation tests (50+ cases)

### Phase 6: Integration & Testing
**Estimated Duration**: 1 week
**Status**: ✓ IMPLEMENTED (end-to-end + tests)
**Remaining tasks**:
- [ ] End-to-end compilation
- [ ] Regression tests
- [ ] Performance benchmarking
- [ ] Documentation updates

---

## Part 4: Comprehensive Test Plan

### Test Matrix

```
┌─────────────────┬──────────┬────────────┬──────────────┐
│ Module          │ Unit     │ Integration│ Total Cases  │
├─────────────────┼──────────┼────────────┼──────────────┤
│ Lexer           │ 40+      │ 15+        │ 55+          │
│ Parser          │ 50+      │ 20+        │ 70+          │
│ Semantics       │ 40+      │ 15+        │ 55+          │
│ IR Generator    │ 30+      │ 10+        │ 40+          │
│ Optimizer       │ 25+      │ 10+        │ 35+          │
│ Code Generator  │ 50+      │ 25+        │ 75+          │
├─────────────────┼──────────┼────────────┼──────────────┤
│ TOTAL           │ 235+     │ 95+        │ 330+ TESTS   │
└─────────────────┴──────────┴────────────┴──────────────┘
```

### Test Categories

#### 1. Lexer Tests (40+ cases)
- Keywords: 10 cases (all C99 keywords)
- Numbers: 8 cases (decimal, hex, octal, float)
- Strings: 6 cases (literals, escapes)
- Operators: 12 cases (arithmetic, logical, bitwise, etc.)
- Delimiters: 5 cases
- Comments: 3 cases
- Edge cases: 5 cases

#### 2. Parser Tests (50+ cases)
- Expressions: 12 cases (binary, unary, ternary, assignment)
- Declarations: 10 cases (variables, functions, structs)
- Statements: 15 cases (if, loops, switch, etc.)
- Type specifiers: 6 cases
- Error recovery: 7 cases

#### 3. Semantic Tests (40+ cases)
- Type checking: 12 cases
- Symbol resolution: 8 cases
- Scope management: 7 cases
- Error detection: 10 cases (undefined vars, type mismatch, etc.)
- struct/union handling: 3 cases

#### 4. IR Generation Tests (30+ cases)
- Expression IR: 10 cases
- Statement IR: 8 cases
- Function calls: 5 cases
- Temporary variable generation: 4 cases
- Basic blocks: 3 cases

#### 5. Optimizer Tests (25+ cases)
- Constant folding: 5 cases
- Constant propagation: 4 cases
- Dead code elimination: 4 cases
- Common subexpression: 4 cases
- Strength reduction: 4 cases
- Loop optimization: 4 cases

#### 6. Code Generation Tests (50+ cases)
- Arithmetic: 6 cases
- Logical/Bitwise: 6 cases
- Comparisons: 4 cases
- Function calls: 8 cases
- Loops: 8 cases
- Arrays: 6 cases
- Pointers: 6 cases

### C99 Feature Test Cases

#### Basic Features
```c
01_integers.c          // int, long, short
02_floats.c           // float, double
03_pointers.c         // *, &, ->, .
04_arrays.c           // [], multi-dimensional
05_structs.c          // struct definition and usage
06_unions.c           // union type
07_enums.c            // enum type
08_functions.c        // function definition and calls
09_recursion.c        // recursive functions
10_control_flow.c     // if, else, switch
```

#### Intermediate Features
```c
11_loops.c            // for, while, do-while
12_operators.c        // all operators with precedence
13_type_casting.c     // explicit type casting
14_bitwise_ops.c      // bitwise operators
15_string_handling.c  // string literals and operations
16_stdio_basic.c      // basic printf/scanf
17_variable_scope.c   // global, local, static
18_function_pointers.c // pointers to functions
19_complex_structs.c  // nested structures
20_macro_defines.c    // basic #define
```

#### Advanced C99 Features
```c
21_variable_length_arrays.c    // int arr[n];
22_designated_initializers.c   // {.field = value}
23_compound_literals.c         // (type){...}
24_inline_functions.c          // inline keyword
25_restrict_qualifier.c        // restrict keyword
26_static_arrays.c             // static in array params
27_complex_declarations.c      // int (*)[5] etc
28_variadic_functions.c        // ... varargs
29_generic_selection.c         // _Generic macro
30_alignof_operator.c          // _Alignof
```

#### Edge Cases & Error Cases
```c
edge_01_deep_nesting.c         // {...{...{...}...}...}
edge_02_large_expressions.c    // ((((a+b)+c)+d)+e)...
edge_03_many_parameters.c      // func(a,b,c,...,z)
edge_04_long_functions.c       // 1000+ lines function
edge_05_many_locals.c          // 100+ local variables

err_01_undefined_variable.c    // Use of undefined var
err_02_type_mismatch.c         // int x = "string"
err_03_syntax_error.c          // Missing semicolon
err_04_dup_declaration.c       // double declaration
err_05_wrong_arguments.c       // func(1,2) but expects 3
```

### Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run specific module tests
pytest tests/test_lexer.py -v
pytest tests/test_parser.py -v
pytest tests/test_codegen.py -v

# Run with coverage
pytest tests/ --cov=pycc --cov-report=html

# Run specific test
pytest tests/test_lexer.py::TestKeywords::test_if_keyword -v
```

---

## Part 5: Usage Examples

### Basic Compilation

```python
from pycc.compiler import Compiler

# Create compiler
compiler = Compiler(optimize=True)

# Compile file
result = compiler.compile_file("hello.c", output="hello.s")

if result.success:
    print("✓ Compilation successful!")
    print(f"Output: {result.output_file}")
else:
    print("✗ Compilation failed:")
    for error in result.errors:
        print(f"  - {error}")
```

### Lexer Usage

```python
from pycc.lexer import Lexer, TokenType

code = "int main() { return 0; }"
lexer = Lexer(code)
tokens = lexer.tokenize()

for token in tokens:
    print(f"{token.type.name:15} {token.value:10} {token.line}:{token.column}")
```

### AST Inspection

```python
from pycc.lexer import Lexer
from pycc.parser import Parser
from pycc.ast_nodes import print_ast

code = """
int add(int a, int b) {
    return a + b;
}
"""

lexer = Lexer(code)
tokens = lexer.tokenize()
parser = Parser(tokens)
ast = parser.parse()

print(print_ast(ast))
```

---

## Part 6: Performance & Optimization

### Compilation Performance
- Target: 1000 lines/second (on average machine)
- Single-pass lexer and parser
- Efficient symbol table with hash tables
- Lazy evaluation where possible

### Generated Code Quality
- Reasonable register allocation
- Proper function calling conventions
- Efficient stack frame management
- Basic optimization passes

### Memory Usage
- Efficient token representation
- AST with no redundant copies
- Streaming IR generation (when possible)

---

## Part 7: Known Limitations

### Phase 1 Limitations
- Preprocessor is partial; see `docs/PREPROCESSOR_C89_CHECKLIST.md`
- No floating point (`float`/`double`) type rules or codegen
- Integer promotions / usual arithmetic conversions are incomplete
- Full initializer support is incomplete (especially aggregates)
- Multi-translation-unit model is incomplete (extern across files, objects, archives)
- Limited standard library coverage (header compatibility depends on preprocessor subset)
- No incremental compilation

### Future Enhancements
1. Preprocessor completeness (macro-expanded includes, full macro expansion semantics, #line tracking)
2. Integer promotions / usual arithmetic conversions and qualifier semantics
3. Multi-translation-unit compilation model and linking workflow
4. More optimization passes
5. Debug symbol generation (-g)
6. Link-time optimization
7. Profile-guided optimization
8. ARM/MIPS backend support
9. WebAssembly backend

---

## Part 8: Project Metrics

### Code Metrics (Target)
- Total lines of code: ~3000-4000
- Test coverage: >90%
- Comment/code ratio: 1:3
- Cyclomatic complexity: <10 per function

### Quality Metrics
- All tests passing: 330+ test cases
- Zero known bugs: Target
- Documentation coverage: 100%
- Code style: PEP 8 compliant

---

## Part 9: Contributing

### Code Style
- PEP 8 compliant
- Type hints for all functions
- Docstrings for all modules/classes/functions
- Comments for complex logic

### Testing Requirements
- All new features require unit tests
- Integration tests for major features
- Minimum 90% code coverage
- All tests passing before merge

### Documentation Requirements
- Docstrings with examples
- README updates
- Architecture documentation
- Inline comments for complex code

---

## Part 10: References

### Compiler Theory
- "Compilers: Principles, Techniques, and Tools" - Dragon Book
- "Engineering a Compiler" - Cooper & Torczon
- "Crafting Interpreters" - Robert Nystrom

### C99 Standard
- ISO/IEC 9899:1999 - C99 Standard
- n1256 - C99 Standard (final revision)

### Existing Compilers
- TCC (Tiny C Compiler)
- GCC (GNU C Compiler)
- Clang/LLVM

---

## Summary

This PyCC compiler project provides:

✓ **Complete architectural design** with modular components
✓ **Phased development plan** with clear milestones
✓ **Comprehensive testing strategy** with 450+ tests in tree
✓ **C89 coverage target** with pragmatic extensions
✓ **Educational value** with well-documented code
✓ **Extensibility** for future enhancements

The project is organized to be completed in 5-6 weeks with clear deliverables at each phase.

---

**Project Status**: Actively progressing toward full C89 coverage; core pipeline is working end-to-end with broad tests. See `docs/C89_ROADMAP.md` and `docs/PREPROCESSOR_C89_CHECKLIST.md`.

**Current Version**: 0.1.0 - Core pipeline working end-to-end (C89 subset)

**Next Steps**: Preprocessor completeness, integer promotions/UAC, multi-translation-unit robustness
