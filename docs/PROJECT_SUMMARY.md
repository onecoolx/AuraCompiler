# AuraCompiler (pycc): Practical C89 Compiler - Project Summary

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
│   ├── parser.py                # Syntax analysis (TODO)
│   ├── ast_nodes.py             # AST definitions (COMPLETE ✓)
│   ├── semantics.py             # Semantic analysis (TODO)
│   ├── ir.py                    # Intermediate representation (TODO)
│   ├── optimizer.py             # Optimization passes (TODO)
│   ├── codegen.py               # Code generation (TODO)
│   └── compiler.py              # Main compiler driver (PARTIAL ✓)
├── tests/
│   ├── __init__.py
│   ├── test_lexer.py            # Lexer unit tests (COMPLETE ✓)
│   ├── test_parser.py           # Parser unit tests (TODO)
│   ├── test_semantics.py        # Semantic tests (TODO)
│   ├── test_codegen.py          # Code gen tests (TODO)
│   ├── test_integration.py      # Integration tests (COMPLETE ✓)
│   └── testcases/               # C source test files (TODO)
├── examples/
│   ├── hello.c                  # Hello world example
│   ├── factorial.c              # Recursive factorial
│   ├── fibonacci.c              # Fibonacci sequence
│   └── arrays.c                 # Array operations
└── setup.py                     # Installation script (TODO)
```

### Current Implementation Status (reality)

**Working end-to-end:** Lexer → Parser → Semantics → IR → Codegen → `as`/`ld`.

**Test status:** `pytest` currently passes (`109 passed`).

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
- No preprocessor (no `#include`, macros, conditional compilation, line control)
- No floating point (`float`/`double`) codegen/type rules
- C89 integer promotions / usual arithmetic conversions not fully modeled
- Full declarator/type grammar coverage is incomplete (many edge cases)
- Initializers are incomplete (especially aggregate initializers)
- Translation-unit / multi-file model is incomplete (`extern` across units, archives, etc.)
- Diagnostics and conformance testing vs `gcc -std=c89` not comprehensive yet

---

## Part 2.5: C89 Conformance Tracker (living)

This section is the **source of truth** for what AuraCompiler supports today and what remains.

Legend: **DONE** = implemented + tested; **PARTIAL** = implemented subset + tested; **TODO** = not implemented.

### Frontend: Lexing / Preprocessing

- **DONE**: Tokens for C operators, delimiters, identifiers, integer/char/string literals, comments.
- **PARTIAL**: Keywords set includes many non-C89 keywords (lexer accepts them).
- **TODO**: Preprocessor (minimum viable): `#include` (textual), `#define` object-like macros, `#if/#ifdef/#ifndef/#else/#elif/#endif`, `#line`, `#error`.

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
- **TODO**: Pointer conversions and more complete pointer arithmetic rules.

### Statements / Control flow

- **DONE**: `if/else`, `for`, `while`, `do/while`, `switch/case/default`, `break/continue`, `goto`/labels.

### Data / Initialization / Linking

- **PARTIAL**: String literals in `.rodata` and basic global initializers.
- **TODO**: Full initializer support (scalars + aggregates), including nested aggregate initialization.
- **TODO**: `.bss/.data` emission for more global/static objects with correct alignment/relocations.
- **TODO**: Multi-translation-unit compilation model (`extern` across files), object file emission + link step orchestration.

### Testing / Compliance

- **DONE**: pytest suite covering many implemented features.
- **TODO**: Systematic conformance suite for C89 (feature matrix + targeted tests) and behavior comparison with `gcc -std=c89`.

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

#### **Parser (parser.py) - TODO**

**Purpose**: Build AST from token stream

**Strategy**: Recursive descent with operator precedence climbing

**Components to Implement**:
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

#### **Symbol Table & Type System (semantics.py) - TODO**

**Purpose**: Track symbols and enforce type rules

**Features**:
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

#### **Intermediate Representation (ir.py) - TODO**

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

#### **Optimizer (optimizer.py) - TODO**

**Purpose**: Improve IR code quality

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

#### **Code Generator (codegen.py) - TODO**

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

### Phase 2: Parser (IN PROGRESS)
**Estimated Duration**: 1 week
**Tasks**:
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
**Tasks**:
- [ ] Symbol table implementation
- [ ] Type system implementation
- [ ] Type checking
- [ ] Scope management
- [ ] Error detection
- [ ] Semantic tests (40+ cases)

### Phase 4: IR Generation & Optimization
**Estimated Duration**: 1 week
**Tasks**:
- [ ] IR instruction definition
- [ ] AST to IR conversion
- [ ] Optimization passes
- [ ] IR tests (30+ cases)

### Phase 5: Code Generation
**Estimated Duration**: 2 weeks
**Tasks**:
- [ ] x86-64 instruction selection
- [ ] Register allocation
- [ ] Function prologue/epilogue
- [ ] Calling convention
- [ ] Code generation tests (50+ cases)

### Phase 6: Integration & Testing
**Estimated Duration**: 1 week
**Tasks**:
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
- No preprocessor (#include, #define, #ifdef)
- No goto/label support (initially)
- Limited standard library support
- No separate compilation
- No incremental compilation

### Future Enhancements
1. Full preprocessor support
2. More optimization passes
3. Multi-file compilation
4. Debug symbol generation (-g)
5. Link-time optimization
6. Profile-guided optimization
7. ARM/MIPS backend support
8. WebAssembly backend

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
✓ **Comprehensive testing strategy** with 330+ test cases
✓ **Full C99 feature support** target
✓ **Educational value** with well-documented code
✓ **Extensibility** for future enhancements

The project is organized to be completed in 5-6 weeks with clear deliverables at each phase.

---

**Project Status**: Phase 1 COMPLETE ✓ | Phase 2-6 IN PROGRESS

**Current Version**: 0.1.0 - Lexer & AST Complete

**Next Steps**: Implement Parser (Phase 2)
