# Aura Compiler Collection

## Overview

AuraCompiler is a complete implementation of a C89 compiler written in pure Python, following the classic three-stage compiler architecture: **frontend (lexer/parser)**, **middle-end (optimization)**, and **backend (code generation)**.

## Features

- **C89 Standard Support**: Comprehensive support for C89 language features
- **Classic Compiler Architecture**: 
  - Lexical Analysis (Tokenization)
  - Syntax Analysis (AST Construction)
  - Semantic Analysis (Type Checking & Symbol Resolution)
  - Intermediate Code Generation (3-Address Code)
  - Optimization Pass (Constant Folding, Dead Code Elimination, etc.)
  - Code Generation (x86-64 Assembly)
  - Assembly to Object Code Conversion
- **Pure Python Implementation**: No external compiler dependencies (except for final linking)
- **Comprehensive Error Reporting**: Detailed error messages with line/column information

## Project Structure

```
pycc/
├── pycc/                          # Main package
│   ├── __init__.py
│   ├── lexer.py                  # Tokenization
│   ├── parser.py                 # Syntax analysis & AST
│   ├── ast_nodes.py              # AST node definitions
│   ├── semantics.py              # Semantic analysis & type checking
│   ├── symbol_table.py           # Symbol table management
│   ├── ir.py                     # Intermediate representation (3-address code)
│   ├── optimizer.py              # IR optimization passes
│   ├── codegen.py                # x86-64 code generation
│   └── compiler.py               # Main compiler driver
├── tests/                         # Test suite
│   ├── test_lexer.py
│   ├── test_parser.py
│   ├── test_semantics.py
│   ├── test_codegen.py
│   ├── test_integration.py
│   └── testcases/                # C source test files
├── examples/                      # Example programs
│   ├── hello.c
│   ├── factorial.c
│   └── fibonacci.c
├── docs/                          # Documentation
│   ├── ARCHITECTURE.md           # Detailed architecture design
│   └── DEVELOPMENT_PLAN.md       # Development plan & roadmap
└── requirements.txt              # Python dependencies
```

## Installation

```bash
git clone https://github.com/yourusername/pycc.git
cd pycc
pip install -r requirements.txt
```

## Usage

```bash
# Compile a C file
python -m pycc.compiler -o output.s input.c

# Compile to object file (requires gas and gcc linker)
python -m pycc.compiler -o output.o input.c

# Compile and link
python -m pycc.compiler -o executable input.c
```

## Quick Start

```python
from pycc.compiler import Compiler

compiler = Compiler()
result = compiler.compile_file("example.c", output="example.s")
if result.success:
    print("Compilation successful!")
    print("Output written to:", result.output_file)
else:
    print("Compilation failed:")
    for error in result.errors:
        print(f"  {error}")
```

## Architecture Overview

### 1. Frontend (Lexer + Parser)
- **Lexer**: Converts source code into tokens
- **Parser**: Builds Abstract Syntax Tree (AST) from tokens

### 2. Middle-End (Optimization)
- Converts AST to 3-Address Code (TAC)
- Constant folding
- Dead code elimination
- Common subexpression elimination
- Loop optimization

### 3. Backend (Code Generation)
- x86-64 assembly generation
- Register allocation
- Stack frame management
- Function prologue/epilogue

## Supported C89 Features

- [ ] Basic data types (int, float, char, double, etc.)
- [ ] Arrays and pointers
- [ ] Structures and unions
- [ ] Functions and recursion
- [ ] Control flow (if, for, while, do-while, switch)
- [ ] Operators (arithmetic, logical, bitwise, comparison)
- [ ] Type casting
- [ ] Standard library function calls (limited)
- [ ] Preprocessor directives (basic support)
- [ ] Variable-length arrays (VLA)
- [ ] Inline functions

## Development Status

- [x] Project structure setup
- [x] Architecture design
- [ ] Lexer implementation
- [ ] Parser implementation
- [ ] AST and symbol table
- [ ] Semantic analysis
- [ ] IR generation
- [ ] Optimizer
- [ ] Code generator
- [ ] Assembler integration
- [ ] Comprehensive testing
- [ ] Documentation

## Testing

```bash
# Run all tests
python -m pytest tests/ -v

# Run specific test
python -m pytest tests/test_lexer.py -v

# Run with coverage
python -m pytest tests/ --cov=pycc --cov-report=html
```

## Contributing

This is an educational compiler project. Contributions are welcome!

## References

- "Compilers: Principles, Techniques, and Tools" (Dragon Book)
- "Engineering a Compiler" by Cooper & Torczon
- TinyCompiler, Crafting Interpreters
- C89 Standard Specification

## License

MIT License - See LICENSE file for details

## Author

Python C Compiler Project Contributors
