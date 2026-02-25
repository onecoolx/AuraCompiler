# AuraCompiler (pycc) Architecture

## 1. Compiler Pipeline Overview

```
Source Code (.c)
    ↓
[LEXER] → Tokens
    ↓
[PARSER] → Abstract Syntax Tree (AST)
    ↓
[SEMANTIC ANALYZER] → Annotated AST + Symbol Table
    ↓
[IR GENERATOR] → 3-Address Code (Intermediate Representation)
    ↓
[OPTIMIZER] → Optimized IR
    ↓
[CODE GENERATOR] → x86-64 Assembly
    ↓
[ASSEMBLER] (`as`) → Object Code (.o)
    ↓
[LINKER] (`ld`) → ELF executable
```

## 2. Module Design

### 2.1 Lexical Analysis (lexer.py)

**Purpose**: Convert source code into a stream of tokens.

**Key Components**:
- `Token` class: Represents a lexical token
  - type (keyword, identifier, number, operator, etc.)
  - value (the actual text)
  - line, column (for error reporting)
  
- `Lexer` class: Tokenizes source code
  - Recognizes C99 keywords
  - Handles identifiers and numbers (decimal, hex, octal, float)
  - Processes string and character literals
  - Handles comments (// and /* */)
  - Manages operator recognition

**Token Types**:
```
KEYWORD: if, else, while, for, int, float, char, return, etc.
IDENTIFIER: variable names, function names
NUMBER: integers (10, 0x10, 010) and floats (3.14, 1.0e-5)
STRING: "hello"
CHAR: 'a'
OPERATOR: +, -, *, /, %, ==, !=, <, >, <=, >=, &&, ||, !, etc.
DELIMITER: (, ), {, }, [, ], ;, :, ?, ,, .
EOF: end of file
```

### 2.2 Syntax Analysis (parser.py, ast_nodes.py)

**Purpose**: Build an Abstract Syntax Tree from tokens.

**AST Node Hierarchy**:
```
ASTNode (base class)
├── Program
├── Declaration
│   ├── FunctionDecl
│   ├── VariableDecl
│   ├── StructDecl
│   └── TypedefDecl
├── Statement
│   ├── CompoundStmt
│   ├── ExpressionStmt
│   ├── IfStmt
│   ├── WhileStmt
│   ├── ForStmt
│   ├── DoWhileStmt
│   ├── SwitchStmt
│   ├── CaseStmt
│   ├── DefaultStmt
│   ├── BreakStmt
│   ├── ContinueStmt
│   ├── ReturnStmt
│   ├── GotoStmt
│   ├── LabelStmt
│   └── DeclStmt
└── Expression
    ├── BinaryOp
    ├── UnaryOp
    ├── TernaryOp
    ├── Assignment
    ├── FunctionCall
    ├── ArrayAccess
    ├── MemberAccess
    ├── PointerDeref
    ├── AddressOf
    ├── Cast
    ├── Literal
    ├── Identifier
    ├── SizeOf
    └── Initializer
```

**Parser Strategy**: Recursive descent parser with operator precedence climbing

**Operator Precedence** (C99):
1. Postfix: ++, --, (), [], ., ->
2. Unary: ++, --, +, -, !, ~, *, &, sizeof, _Alignof
3. Multiplicative: *, /, %
4. Additive: +, -
5. Shift: <<, >>
6. Relational: <, >, <=, >=
7. Equality: ==, !=
8. Bitwise AND: &
9. Bitwise XOR: ^
10. Bitwise OR: |
11. Logical AND: &&
12. Logical OR: ||
13. Conditional: ?:
14. Assignment: =, +=, -=, *=, /=, %=, <<=, >>=, &=, ^=, |=
15. Comma: ,

### 2.3 Semantic Analysis (semantics.py, symbol_table.py)

**Purpose**: Type checking, symbol resolution, and semantic validation.

**Symbol Table**:
- Manages scope (global, function, block)
- Stores variable/function declarations
- Tracks type information
- Supports nested scopes with proper shadowing

**Operations**:
- Type checking for assignments and operations
- Function signature validation
- Array bounds checking (compile-time)
- Undefined symbol detection
- Type conversion validation
- struct/union member resolution

**Semantic Errors Detected**:
- Undefined variables/functions
- Type mismatch in assignments
- Invalid operations for types
- Duplicate declarations
- Return type mismatch
- Array indexing on non-arrays
- Dereferencing non-pointers

### 2.4 Intermediate Representation (ir.py)

**Purpose**: Convert AST to a minimal TAC-like instruction list tailored for the current code generator.

**3-Address Code Format**:
```
result = operand1 op operand2
goto label
if condition goto label
function_call(arg1, arg2, ...)
return value
```

**IR Instruction Types (current subset)**:
```
BinOp: x = y op z
UnaryOp: x = op y
Assignment: x = y
Copy: x = y
Call: x = call func(args)
Return: return x
Goto: goto label
CondGoto: if cond goto label
Label: label: (includes user labels for `goto`)
Param: param x (for function calls)
```

**Temporary Variables**:
- Generated for intermediate computations
- Named t0, t1, t2, ... (for SSA-like form during generation)

### 2.5 Optimizer (optimizer.py)

**Purpose**: Perform IR-level optimizations.

**Optimization Passes**:
1. **Constant Folding**: Evaluate constant expressions at compile time
   - 2 + 3 → 5
   - 1 < 2 → 1

2. **Constant Propagation**: Replace variables with constant values
   - x = 5; y = x; → y = 5;

3. **Dead Code Elimination**: Remove unused assignments
   - x = 5; (x never used) → remove

4. **Common Subexpression Elimination**:
   - a = b + c; d = b + c; → a = b + c; d = a;

5. **Loop Optimization**:
   - Loop unrolling (limited)
   - Invariant code motion

6. **Peephole Optimization**:
   - Pattern matching on instruction sequences

### 2.6 Code Generation (codegen.py)

**Purpose**: Generate x86-64 assembly code.

**Target Architecture**: x86-64 (System V AMD64 ABI for Linux)

**Toolchain**:
- Assemble with `as` (override via `PYCC_AS`)
- Link with `ld` (override via `PYCC_LD`)
- Linker command attempts to detect a usable C runtime (glibc dev preferred; fallback newlib)

**Key Features**:
- Calling conventions (System V AMD64)
  - Arguments: rdi, rsi, rdx, rcx, r8, r9 (first 6 integer args)
  - Return value: rax/rdx:rax
  - Callee-saved: rbx, rbp, r12-r15
  - Caller-saved: rax, rcx, rdx, rsi, rdi, r8-r11

- Function prologue/epilogue generation
- Stack frame management
- Register allocation (simple greedy)
- Basic block identification
- Label and jump handling

**Assembly Sections**:
```
.section .data        # Initialized global data
.section .bss         # Uninitialized global data
.section .rodata      # Read-only data (strings, constants)
.section .text        # Code
```

**Generated Code Quality**:
- Readable assembly with comments
- Efficient register usage
- Proper memory alignment

### 2.7 Compiler Driver (compiler.py)

**Purpose**: Orchestrate the compilation pipeline.

**Main Compiler Class**:
```python
class Compiler:
    def compile_file(source_file, output_file=None, optimize=True)
    def compile_code(source_code, output_file=None, optimize=True)
    
    def get_tokens(source_code) -> List[Token]
    def get_ast(source_code) -> AST
    def get_ir(source_code) -> List[IRInstruction]
    def get_assembly(source_code) -> str
```

**Compilation Phases**:
1. Source reading
2. Lexical analysis
3. Syntax analysis
4. Semantic analysis
5. IR generation
6. Optimization (if enabled)
7. Code generation
8. Output writing

## 3. Data Structure Design

### 3.1 Token Structure
```python
@dataclass
class Token:
    type: str           # 'keyword', 'identifier', 'number', etc.
    value: str          # The actual token text
    line: int           # Source line number
    column: int         # Column in the line
```

### 3.2 AST Node Base Class
```python
@dataclass
class ASTNode:
    line: int
    column: int
    # ... specific fields for each node type
```

### 3.3 Type System
```python
@dataclass
class Type:
    base: str           # 'int', 'float', 'char', 'struct', 'union', etc.
    is_pointer: bool
    is_array: bool
    array_size: Optional[int]
    is_const: bool
    is_volatile: bool
    struct_name: Optional[str]
```

### 3.4 Symbol Table Entry
```python
@dataclass
class Symbol:
    name: str
    type: Type
    kind: str           # 'variable', 'function', 'typedef', etc.
    scope: int          # Scope depth
    offset: int         # Memory offset (for local variables)
    is_extern: bool
    initializer: Optional[Expression]
```

### 3.5 IR Instruction
```python
@dataclass
class IRInstruction:
    op: str             # 'add', 'sub', 'call', 'goto', etc.
    result: Optional[str]      # Destination (temp or variable)
    operand1: Optional[str]    # First operand
    operand2: Optional[str]    # Second operand (for binary ops)
    label: Optional[str]       # For jump instructions
    args: Optional[List]       # For function calls
    line: int
```

## 4. Type System

**Primitive Types**:
- void
- char (8-bit)
- short (16-bit)
- int (32-bit)
- long (64-bit)
- long long (64-bit)
- float (32-bit IEEE 754)
- double (64-bit IEEE 754)
- Qualifiers: const, volatile, restrict

**Derived Types**:
- Pointers: int*, char**
- Arrays: int[10], float[5][3]
- Functions: int (*func)(int, int)
- Structures: struct Point { int x; int y; }
- Unions: union Data { int i; float f; }

**Type Conversions**:
- Implicit conversions (int to float, char to int, etc.)
- Explicit casts: (type)expression

## 5. Error Handling

**Error Categories**:
- **Syntax Errors**: Unexpected tokens, malformed statements
- **Semantic Errors**: Type mismatches, undefined symbols
- **Compilation Errors**: Code generation failures

**Error Information**:
- Error message
- Source file location (line:column)
- Context (surrounding code)
- Suggestions for fixes

## 6. Extension Points

### 6.1 Adding New Optimizations
- Implement new optimization pass in `optimizer.py`
- Register pass in optimization pipeline

### 6.2 Adding Language Features
- Add tokens to lexer
- Extend AST node types
- Add parsing rules
- Update semantic analysis
- Generate IR for new constructs
- Update code generator

### 6.3 Supporting New Architectures
- Implement new code generator (e.g., ARM)
- Define calling conventions
- Register allocation strategy
- Instruction selection

## 7. C99 Feature Support Matrix

| Feature | Status |
|---------|--------|
| Basic data types | ✓ |
| Pointers | ✓ |
| Arrays | ✓ |
| Functions | ✓ |
| Structs/Unions | ✓ |
| Control flow | ✓ |
| Operators | ✓ |
| Type casting | ✓ |
| Variable-length arrays | ⟳ |
| Designated initializers | ⟳ |
| Compound literals | ⟳ |
| Inline functions | ⟳ |
| Restrict pointers | ⟳ |

Legend: ✓ Completed, ⟳ Partial, ✗ Not implemented

## 8. Performance Considerations

- Single-pass lexer and parser
- Efficient symbol table lookups (hash tables)
- IR optimization before code generation
- Minimal memory overhead
- Reasonable compilation speed for educational purposes

## 9. Testing Strategy

- **Unit Tests**: Test each module independently
- **Integration Tests**: Test compilation pipeline end-to-end
- **Regression Tests**: Prevent feature breakage
- **Test Cases**: Cover C99 language features
- **Edge Cases**: Error handling, boundary conditions

