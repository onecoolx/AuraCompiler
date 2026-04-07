# AuraCompiler

Practical **C89/ANSI C** compiler in **Python**.

Generates **x86-64 SysV** assembly and uses **binutils `as`/`ld`** to produce ELF executables.

## Features (current)

- **C89 subset** with growing coverage, validated by `pytest`
- **Classic Compiler Architecture**: 
  - Lexical Analysis (Tokenization)
  - Syntax Analysis (AST Construction)
  - Semantic Analysis (Type Checking & Symbol Resolution)
  - IR Generation (minimal TAC-like instruction list)
  - Optimizer (currently minimal)
  - Code Generation (x86-64 Assembly)
  - Assemble/link via `as`/`ld`
- **Pure Python Implementation**: No external compiler dependencies (except for final linking)
- **Comprehensive Error Reporting**: Detailed error messages with file/line/column information

### Implemented language features (high level)

- Declarations: globals/locals, `static`/`extern`, function prototypes + definitions, multi-declarator (`int a, b;`)
- Types: `int`, `char`, `short`, `long` (signed/unsigned), `float`, `double`, pointers, arrays, `typedef`
- Aggregates: `struct`/`union` (layout + member access `.` / `->`, bit-fields, `typedef struct {} T;`)
- Control flow: `if/else`, `for`, `while`, `do/while`, `switch/case/default`, `break/continue`, `goto`/labels
- Expressions: arithmetic/bitwise/compare, assignment, `++`/`--` (pre/post), calls, `?:`, `&`, member access
- Operators: `sizeof` (incl. struct/union), C-style cast `(type)expr`, comma operator
- Enums: `enum` definitions + enumerator constants
- Floating point: `float`/`double` literals, arithmetic, comparisons, int↔float casts, function params/return (SSE/SSE2)
- Preprocessor: `#define`/`#undef`, `#include`, `#if`/`#ifdef`/`#elif`/`#else`, `#`/`##`, `#line`, trigraphs
- String literals: adjacent concatenation (`"ab" "cd"`), wide chars (`L'x'`, `L"str"`)

## Project Structure

```
pycc/
├── pycc/                          # Main package
│   ├── __init__.py
│   ├── lexer.py                  # Tokenization
│   ├── parser.py                 # Syntax analysis & AST
│   ├── ast_nodes.py              # AST node definitions
│   ├── types.py                  # Structured C89 type system (CType)
│   ├── semantics.py              # Semantic analysis & type checking
│   ├── ir.py                     # Intermediate representation (3-address code)
│   ├── optimizer.py              # IR optimization passes
│   ├── codegen.py                # x86-64 code generation (incl. SSE/SSE2)
│   ├── preprocessor.py           # C preprocessor (built-in + PPToken engine)
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
# Compile to assembly
python pycc.py -o output.s input.c

# Compile to object
python pycc.py -o output.o input.c

# Compile + link to executable
python pycc.py -o a.out input.c

# Preprocess only (emit preprocessed C to stdout)
python pycc.py -E input.c

# Prefer system preprocessor (recommended for glibc headers)
python pycc.py --use-system-cpp -o a.out input.c
```

Preprocessor-related options:

- `-E` preprocess only (write to stdout or `-o`)
- `--use-system-cpp` preprocess via system `gcc -E` (recommended for system headers)
- `-I DIR` add include directory (affects both preprocessors)
- `-D NAME[=VALUE]` / `-U NAME` define/undefine macros

Toolchain overrides:

- `PYCC_AS=...` override assembler (default: `as`)
- `PYCC_LD=...` override linker (default: `ld`)

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

### 2. Middle-End (Semantic Analysis + IR)
- Structured type system (`CType` hierarchy) with integer promotion and UAC
- const/volatile enforcement, pointer compatibility checks
- Converts AST to 3-Address Code (TAC) with float-aware IR (fmov/fadd/fsub/fmul/fdiv/fcmp)
- Constant folding

### 3. Backend (Code Generation)
- x86-64 assembly generation
- Integer ops via general-purpose registers
- Float ops via SSE/SSE2 (xmm registers, .rodata literals)
- Stack frame management
- Function prologue/epilogue

## Notes / current limitations

- Not a full C89 implementation yet (work in progress).
- Preprocessor has both a built-in token engine and system `cpp` mode; see `docs/PREPROCESSOR_C89_CHECKLIST.md`.
- Structured type system (`pycc/types.py`) with CType hierarchy, integer promotion, and UAC.
- `&&`/`||` are short-circuiting.
- Floating point: `float`/`double` variables, arithmetic, comparisons, and int↔float casts via SSE/SSE2.

## Preprocessing modes (recommended)

AuraCompiler supports two practical ways to handle preprocessing; keeping both makes the tool behave closer to a “real” toolchain:

1) **System preprocessor mode** (recommended for system headers)
  - Use your platform's `cpp` to expand headers/macros, then compile the preprocessed output.
  - This offers the best compatibility with glibc headers.

2) **Built-in preprocessor mode** (portable subset)
  - Uses `pycc/preprocessor.py`.
  - Supports a broad subset but is not a full C preprocessor; some macro corner cases are intentionally unsupported.

## Development status

See `docs/C89_ROADMAP.md`.

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

Zhang Ji Peng (onecoolx@gmail.com)
