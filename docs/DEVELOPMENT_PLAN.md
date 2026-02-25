# AuraCompiler (pycc) Development Plan & Roadmap

This document is a **living plan**. It reflects the current repo reality and is updated as features land.

Current test status: `pytest` passes (`109 passed`).

## Status Summary (Reality)

The compiler already works end-to-end for a practical C89 subset:

- Lexer → Parser → Semantics → IR → Optimizer → x86-64 codegen → `as`/`ld`
- Covered by a reasonably broad pytest suite.

However, it is **not yet fully conforming C89**. The remaining work is tracked below.

## Roadmap to Full C89 (Detailed)

Legend: **DONE** = implemented + tested; **PARTIAL** = implemented subset + tested; **TODO** = not implemented.

### Phase A — Preprocessing (required for real-world C89)

- [ ] **TODO** Implement a preprocessor stage in the driver
  - [ ] `#include` (at least quoted includes + include paths)
  - [ ] Object-like macros (`#define NAME value`) and simple expansion
  - [ ] Conditional compilation: `#if/#ifdef/#ifndef/#elif/#else/#endif`
  - [ ] `#line` tracking for correct diagnostics
  - [ ] `#error`
  - Acceptance: compile programs that use `<stdio.h>` via `#include` (with a minimal shim or system headers subset)
  - Tests: unit tests for macro expansion + integration tests compiling code using `#include`.

### Phase B — Type System Correctness (C89 core rules)

- [ ] **TODO** Integer promotions + usual arithmetic conversions
  - Scope: `char/short/int/long`, signed/unsigned interactions, comparison and arithmetic, shifts
  - Acceptance: match `gcc -std=c89` results for a curated set of expressions
  - Tests: expression-level compile+run tests (return codes), plus semantic typing tests.

- [ ] **TODO** Qualifiers (`const`, `volatile`) and more accurate lvalue rules
  - Acceptance: reject invalid writes to const objects; preserve qualifiers through pointers where applicable
  - Tests: semantic error tests.

- [ ] **TODO** Pointer conversion rules and pointer arithmetic completeness
  - Acceptance: common idioms compile, invalid cases rejected (best-effort)
  - Tests: compile+run pointer tests.

### Phase C — Declarations / Declarators Completion

- [ ] **TODO** Complete declarator grammar coverage
  - Function pointers, nested declarators, arrays-of-pointers vs pointer-to-array, etc.
  - Acceptance: parse/compile a corpus of declarator patterns
  - Tests: parser tests + small codegen tests.

- [ ] **OPTIONAL** Old-style K&R function definitions (C89)
  - Acceptance: parse and compile K&R-style parameter declarations
  - Tests: parser + integration.

### Phase D — Initialization / Data Layout / Linkage

- [ ] **TODO** Full initializer support (scalars + aggregates)
  - Arrays, structs, nested braces, partial initialization, string init for `char[]`
  - Acceptance: match `gcc -std=c89` initialization outcomes for curated cases
  - Tests: compile+run tests for initialized globals and locals.

- [ ] **TODO** Global/static data emission completeness
  - `.data/.bss/.rodata` placement, alignment, relocations for pointers, zero-fill
  - Tests: inspect output behavior via run tests (and possibly assembly pattern tests if stable).

- [ ] **TODO** Multi-translation-unit build model
  - `extern` across files, multiple source inputs → objects → link
  - Tests: integration tests compiling two `.c` files and linking.

### Phase E — Diagnostics & Conformance

- [ ] **TODO** Expand diagnostics and warnings
  - Duplicate/compatible declarations, incomplete types, invalid casts, etc.

- [ ] **TODO** Conformance suite vs `gcc -std=c89`
  - Maintain a feature matrix and a set of comparison tests
  - Acceptance: all tracked features marked DONE/PARTIAL have corresponding tests.

---

## Historical Plan (kept for reference)

### Phase 1: Core Infrastructure (Week 1)
**Objective**: Establish basic compiler framework

#### Task 1.1: Lexer Implementation (2 days)
- [ ] Create `Token` class with type, value, line, column
- [ ] Implement `Lexer` class for tokenization
- [ ] Support C99 keywords (if, else, while, for, int, float, char, void, return, etc.)
- [ ] Handle identifiers and numbers (decimal, hex, octal, float literals)
- [ ] Process string and character literals with escape sequences
- [ ] Support single-line (//) and multi-line (/* */) comments
- [ ] Operator recognition (arithmetic, logical, bitwise, comparison, assignment)
- [ ] Error handling for invalid tokens
- **Test**: Unit tests for various token types

#### Task 1.2: AST Node Definition (1 day)
- [ ] Define `ASTNode` base class
- [ ] Create node classes for all language constructs:
  - Declarations: FunctionDecl, VariableDecl, StructDecl, TypedefDecl
  - Statements: CompoundStmt, IfStmt, WhileStmt, ForStmt, etc.
  - Expressions: BinaryOp, UnaryOp, FunctionCall, etc.
- [ ] Add line/column information to all nodes
- [ ] Create helper methods for AST traversal

#### Task 1.3: Basic Parser (2.5 days)
- [ ] Implement recursive descent parser
- [ ] Parse program structure (declarations and definitions)
- [ ] Parse function declarations and definitions
- [ ] Parse variable declarations
- [ ] Parse simple statements (expression statements, return)
- [ ] Parse control flow (if-else, while, for, do-while, switch)
- [ ] Parse expressions with operator precedence
- [ ] Error recovery mechanisms
- **Test**: Unit tests for various C99 constructs

### Phase 2: Symbol Table & Semantic Analysis (Week 2)
**Objective**: Enable type checking and symbol resolution

#### Task 2.1: Symbol Table Implementation (1 day)
- [ ] Implement `Symbol` class with type and scope information
- [ ] Create `SymbolTable` class with scope management
- [ ] Support nested scopes (global, function, block)
- [ ] Implement lookup with scope chain traversal
- [ ] Handle variable shadowing properly
- [ ] Track function signatures

#### Task 2.2: Type System (1.5 days)
- [ ] Define `Type` class supporting:
  - Primitive types: int, float, char, double, void, etc.
  - Qualifiers: const, volatile
  - Derived types: pointers, arrays
  - Aggregate types: struct, union
- [ ] Implement type compatibility checking
- [ ] Support implicit type conversions
- [ ] Type promotion rules (int → long → float → double)

#### Task 2.3: Semantic Analysis (2 days)
- [ ] Type checking for assignments
- [ ] Function call validation (argument count, types)
- [ ] Array bounds checking (at compile time if possible)
- [ ] Undefined symbol detection
- [ ] Duplicate declaration detection
- [ ] Return type validation
- [ ] Pointer and array operations validation
- [ ] struct/union member resolution
- **Test**: Semantic error detection tests

### Phase 3: Intermediate Representation (Week 3)
**Objective**: Generate and optimize intermediate code

#### Task 3.1: IR Design and Generation (2.5 days)
- [ ] Define `IRInstruction` class
- [ ] Implement 3-Address Code (TAC) generation:
  - Binary operations: x = y op z
  - Unary operations: x = op y
  - Assignments: x = y
  - Function calls: x = call func(args)
  - Jumps and labels
  - Return statements
- [ ] Handle temporary variable generation
- [ ] Convert AST to IR
- [ ] Support function calls and returns
- [ ] Proper basic block identification
- **Test**: IR generation correctness tests

#### Task 3.2: Optimizer (1.5 days)
- [ ] Constant folding:
  - Evaluate constant expressions at compile time
  - 2 + 3 → 5, 1 < 2 → true
- [ ] Constant propagation
- [ ] Dead code elimination
- [ ] Common subexpression elimination (basic)
- [ ] Strength reduction (e.g., x*2 → x<<1)
- **Test**: Optimization correctness tests

### Phase 4: Code Generation (Week 4)
**Objective**: Generate x86-64 assembly code

#### Task 4.1: Basic Code Generation (2.5 days)
- [ ] x86-64 instruction set support
- [ ] Register allocation (simple greedy strategy)
- [ ] Function prologue/epilogue generation:
  - Stack frame setup
  - Register preservation (callee-saved)
- [ ] Function call handling:
  - Argument passing (System V AMD64 ABI)
  - Return value handling
- [ ] Variable memory allocation
- [ ] Array and struct layout
- [ ] Label and jump generation

#### Task 4.2: Expression Code Generation (1.5 days)
- [ ] Arithmetic operations
- [ ] Logical and bitwise operations
- [ ] Comparison operations
- [ ] Pointer dereferencing
- [ ] Array indexing
- [ ] Function calls
- [ ] Cast operations

#### Task 4.3: Statement Code Generation (1 day)
- [ ] Assignment statements
- [ ] Control flow (if-else, loops)
- [ ] Function returns
- [ ] Label/goto support
- **Test**: Code generation correctness tests

### Phase 5: Testing & Refinement (Week 5)
**Objective**: Comprehensive testing and bug fixing

#### Task 5.1: Lexer Testing (0.5 days)
- [ ] Test all token types
- [ ] Test edge cases (large numbers, long strings)
- [ ] Test error handling

#### Task 5.2: Parser Testing (1 day)
- [ ] Test all language constructs
- [ ] Test operator precedence
- [ ] Test nested structures
- [ ] Test error recovery

#### Task 5.3: Integration Testing (1 day)
- [ ] End-to-end compilation tests
- [ ] Test with standard C programs:
  - Hello world
  - Factorial (recursion)
  - Fibonacci
  - Array manipulation
  - Struct usage
  - Pointer operations
- [ ] Test optimization passes

#### Task 5.4: Regression Testing (1 day)
- [ ] Create comprehensive test suite
- [ ] Test C99 specific features:
  - Variable declarations in for loops
  - Array variable-length arrays
  - Designated initializers
  - Inline functions
  - restrict pointer qualifier
- [ ] Performance benchmarks

#### Task 5.5: Documentation & Examples (1 day)
- [ ] API documentation
- [ ] Usage examples
- [ ] Implementation notes
- [ ] Known limitations

## Detailed Test Plan

### Unit Tests

#### Lexer Tests (test_lexer.py)
```
test_keywords()          # Test all C99 keywords
test_identifiers()       # Test identifier recognition
test_integers()          # Test int literals (10, 0x10, 010)
test_floats()           # Test float literals (3.14, 1.0e-5)
test_strings()          # Test string literals with escape sequences
test_characters()       # Test character literals
test_operators()        # Test all operators
test_comments()         # Test single and multi-line comments
test_error_handling()   # Test error cases
```

#### Parser Tests (test_parser.py)
```
test_function_declaration()     # Parse function declarations
test_variable_declaration()     # Parse variable declarations
test_struct_definition()        # Parse struct/union definitions
test_if_statement()             # Parse if-else statements
test_loop_statements()          # Parse while, for, do-while
test_switch_statement()         # Parse switch-case statements
test_expression_parsing()       # Parse various expressions
test_operator_precedence()      # Test operator precedence
test_array_access()             # Parse array indexing
test_pointer_operations()       # Parse pointer operations
test_function_calls()           # Parse function calls
test_type_casting()             # Parse type casts
test_error_recovery()           # Test parser error recovery
```

#### Semantic Tests (test_semantics.py)
```
test_type_checking()            # Type compatibility checking
test_function_signatures()      # Function argument type checking
test_undefined_symbols()        # Detection of undefined variables
test_duplicate_declarations()   # Detection of duplicate declarations
test_type_conversions()         # Implicit type conversions
test_struct_member_access()     # Struct field resolution
test_pointer_dereferencing()    # Pointer operation validation
test_array_operations()         # Array indexing validation
test_return_types()             # Function return type validation
test_scope_management()         # Variable shadowing and scope
```

#### Code Generation Tests (test_codegen.py)
```
test_arithmetic_operations()    # Addition, subtraction, multiplication, division
test_logical_operations()       # AND, OR, NOT operations
test_bitwise_operations()       # Bit manipulation operations
test_comparison_operations()    # Comparison operators
test_function_generation()      # Function prologue/epilogue
test_function_calls()           # Function call code generation
test_variable_allocation()      # Variable memory allocation
test_array_generation()         # Array layout and indexing
test_pointer_operations()       # Pointer dereferencing in code
test_control_flow()             # If-else, loops in generated code
```

### Integration Tests (test_integration.py)

#### Basic Programs
```
hello_world()
  Input: printf("Hello, World!\n");
  Verify: Correct assembly generated

simple_arithmetic()
  Input: int main() { int x = 5; int y = 3; return x + y; }
  Verify: Returns 8

factorial()
  Input: Recursive factorial function
  Verify: Correct computation for various inputs

fibonacci()
  Input: Fibonacci function
  Verify: Correct sequence generation

array_operations()
  Input: Array initialization and manipulation
  Verify: Correct array indexing and iteration

pointer_operations()
  Input: Pointer declaration, dereferencing, arithmetic
  Verify: Correct memory access patterns

struct_usage()
  Input: Struct definition and member access
  Verify: Correct struct layout and member access

string_operations()
  Input: String literal handling and manipulation
  Verify: Correct string operations
```

#### C99 Features
```
variable_length_arrays()
  Input: int n = 5; int arr[n];
  Verify: VLA support

designated_initializers()
  Input: struct Point p = {.x = 1, .y = 2};
  Verify: Designated initializer support

for_loop_declarations()
  Input: for (int i = 0; i < 10; i++)
  Verify: C99 for loop variable declaration

compound_literals()
  Input: (struct Point){1, 2}
  Verify: Compound literal support

inline_functions()
  Input: inline int add(int a, int b) { return a + b; }
  Verify: Inline function handling
```

### Test Case Files (tests/testcases/)

#### Basic Tests
```
01_hello.c              # Hello world
02_arithmetic.c         # Basic arithmetic
03_variables.c          # Variable declaration and usage
04_functions.c          # Function definition and calls
05_control_flow.c       # If-else statements
06_loops.c              # For and while loops
07_arrays.c             # Array declaration and access
08_pointers.c           # Pointer operations
09_structs.c            # Structure definition and usage
10_unions.c             # Union types
```

#### Intermediate Tests
```
11_recursion.c          # Recursive functions
12_nested_functions.c   # Nested function calls
13_multidim_arrays.c    # Multidimensional arrays
14_pointer_arithmetic.c # Pointer operations
15_dynamic_structs.c    # Complex struct definitions
16_type_casting.c       # Explicit and implicit type conversions
17_bitwise_ops.c        # Bitwise operations
18_switch_case.c        # Switch statement
19_goto_labels.c        # Label and goto
20_enums.c              # Enumeration types
```

#### Advanced Tests
```
21_vla_arrays.c         # Variable-length arrays
22_designated_init.c    # Designated initializers
23_compound_literals.c  # Compound literals
24_inline_funcs.c       # Inline functions
25_restrict_ptr.c       # Restrict pointer qualifier
26_complex_structs.c    # Complex struct nesting
27_array_of_ptrs.c      # Array of pointers
28_ptr_to_arrays.c      # Pointer to arrays
29_function_ptrs.c      # Function pointers
30_recursive_structs.c  # Recursive struct definitions
```

#### Edge Cases
```
edge_01_empty_file.c    # Empty source file
edge_02_only_comments.c # Only comments
edge_03_large_numbers.c # Large integer literals
edge_04_deep_nesting.c  # Deeply nested structures
edge_05_long_functions.c# Very long function
edge_06_many_vars.c     # Many variable declarations
edge_07_complex_expr.c  # Complex expression evaluation
edge_08_type_overflow.c # Type range boundaries
```

#### Error Cases
```
err_01_syntax_error.c   # Malformed statement
err_02_undefined_var.c  # Undefined variable usage
err_03_type_mismatch.c  # Type mismatch in assignment
err_04_dup_declaration.c# Duplicate variable declaration
err_05_invalid_cast.c   # Invalid type cast
err_06_wrong_args.c     # Wrong function arguments
err_07_break_outside.c  # Break outside loop
err_08_return_type.c    # Wrong return type
```

## Compilation & Execution Strategy

### Phase 1: Assembly Generation (Current)
Output: x86-64 assembly (.s file)
```bash
python -m pycc.compiler input.c -o output.s
```

### Phase 2: Object File Generation
- Use external assembler (as/gas) to assemble .s → .o
- Link with standard C library if needed

### Phase 3: Full Executable
- Link .o files with libc and other libraries
- Use ld or gcc for linking

## Success Criteria

1. **Lexer**: Correctly tokenizes 100% of C99 token types
2. **Parser**: Builds correct AST for all tested C99 constructs
3. **Semantics**: Detects semantic errors with high precision
4. **Code Gen**: Generates correct assembly for all constructs
5. **Optimization**: Measurable compilation speed and code quality improvements
6. **Testing**: ≥90% code coverage, all test cases pass
7. **Documentation**: Complete API docs, usage examples, implementation notes

## Known Limitations & Future Enhancements

### Current Limitations
- No support for variable-length arrays (initially)
- Limited standard library function support
- No preprocessor (macro expansion, #include)
- No goto/label support initially
- No optimization of loops initially
- Single-pass compilation (no separate compilation)

### Future Enhancements
- [ ] Preprocessor support (#define, #include, #ifdef)
- [ ] More optimization passes (loop unrolling, vectorization)
- [ ] Support for static inline functions
- [ ] Linker optimization (-O2, -O3)
- [ ] Debug symbol generation (-g)
- [ ] Profile-guided optimization
- [ ] Multiple target architectures (ARM, MIPS)
- [ ] Incremental compilation
- [ ] Parallel compilation of multiple files

## Milestone Checklist

- [ ] Milestone 1: Lexer + Parser complete and tested
- [ ] Milestone 2: Semantic analysis complete
- [ ] Milestone 3: IR generation and optimization complete
- [ ] Milestone 4: Code generation complete
- [ ] Milestone 5: Integration tests passing
- [ ] Milestone 6: Full documentation complete
- [ ] Release 1.0: All features stable, comprehensive test coverage

## Resource Requirements

- **Python Version**: 3.8+
- **External Tools**: gcc/as for assembly (optional)
- **Development Time**: ~4-5 weeks for basic implementation
- **Testing Infrastructure**: pytest, coverage tools

## Communication & Collaboration

- Regular progress updates
- Bug tracking and issue management
- Code review process
- Documentation updates
- Community feedback integration
