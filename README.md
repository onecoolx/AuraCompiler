# AuraCompiler

Practical **C89/ANSI C** compiler written in **Python**, targeting **x86-64 SysV Linux**.

Compiles real-world C projects using only **binutils `as`/`ld`** — no gcc dependency for linking.

## Current Status

- Compiles and runs real-world open-source C projects
- Comprehensive test suite with property-based testing

## Features

### Language Support (C89 subset)

- **Types**: `int`, `char`, `short`, `long` (signed/unsigned), `float`, `double`, `long double`, `void`, pointers, arrays, `typedef`, `enum`
- **Aggregates**: `struct`/`union` with layout, member access (`.`/`->`), nested structs, bit-fields, by-value assignment/param/return
- **Control flow**: `if`/`else`, `for`, `while`, `do`/`while`, `switch`/`case`/`default`, `break`/`continue`, `goto`/labels
- **Expressions**: arithmetic, bitwise, comparison, assignment, `++`/`--` (pre/post), function calls, `?:`, `sizeof`, cast, comma operator
- **Compound assignment on members**: `p->val += n`, `s.val++` (full load-op-store semantics)
- **Designated initializers**: `.member = val`, `[index] = val`, nested, mixed with sequential
- **Struct array initializers**: `struct S arr[N] = {{...}, {...}}`
- **Floating point**: SSE/SSE2 for `float`/`double`, x87 for `long double`, implicit int↔float conversion in function calls
- **Variadic functions**: `va_start`/`va_arg`/`va_end` (SysV AMD64 ABI)
- **Volatile**: `volatile` qualifier with memory-access enforcement
- **Function pointers**: type compatibility checks, indirect calls through struct members
- **String literals**: adjacent concatenation, wide chars (`L'x'`, `L"str"`)

### Preprocessor

- `#include` (with search paths), `#define`/`#undef` (object/function-like macros)
- `#if`/`#ifdef`/`#ifndef`/`#elif`/`#else`/`#endif`, `#line`, `#error`, `#warning`
- `#pragma once`, variadic macros, `#`/`##` operators, hide-set algorithm
- Trigraph support
- System preprocessor mode (`gcc -E`) for full glibc header compatibility

### Compiler Architecture

```
Source (.c) → Lexer → Parser → Semantic Analyzer → IR Generator → Optimizer → Code Generator → as → ld → ELF
```

- **Type System**: Structured `CType` hierarchy (`IntegerType`, `PointerType`, `StructType`, etc.) with typedef resolution, integer promotion, usual arithmetic conversions, and native array/pointer distinction (`Type.is_array`)
- **TypedSymbolTable**: Centralized symbol-to-CType mapping shared between IR generation and codegen, with per-function scope archival
- **Toolchain**: Independent `as`/`ld` integration with automatic CRT and library path probing (no gcc dependency)

### Toolchain Independence

AuraCompiler depends only on:
- **`as`** (GNU assembler) — for assembling generated x86-64 assembly
- **`ld`** (GNU linker) — for linking with glibc CRT files
- **glibc-dev** (or equivalent) — for C runtime startup files and standard library

No dependency on `gcc` or `clang` for compilation or linking.

## Project Structure

```
├── pycc.py                        # CLI driver
├── pycc/                          # Compiler package
│   ├── lexer.py                   # Tokenization
│   ├── parser.py                  # Recursive descent parser → AST
│   ├── ast_nodes.py               # AST node definitions
│   ├── types.py                   # CType hierarchy + TypedSymbolTable
│   ├── semantics.py               # Type checking, symbol resolution
│   ├── ir.py                      # 3-address code IR generation
│   ├── optimizer.py               # IR optimization passes
│   ├── codegen.py                 # x86-64 SysV code generation
│   ├── toolchain.py               # Assembler/linker discovery and invocation
│   ├── preprocessor.py            # Built-in C preprocessor
│   ├── builtins.py                # GCC builtin function registry
│   ├── compiler.py                # Compilation pipeline orchestrator
│   └── gcc_extensions.py          # System header compatibility
├── tests/                         # Test suite
├── examples/                      # Example C programs
├── docs/                          # Documentation
│   ├── ARCHITECTURE.md            # Detailed architecture design
│   ├── PROJECT_SUMMARY.md         # Project introduction
│   ├── C89_ROADMAP.md             # Language feature roadmap
│   ├── C89_CONFORMANCE_MATRIX.md  # C89 conformance tracking
│   ├── FEATURE_TRACKER.md         # Feature status
│   ├── NEXT_PLAN.md               # Next major refactoring plan
│   └── ...
└── requirements.txt               # Python dependencies (pytest)
```

## Installation

```bash
git clone https://github.com/AuraCompiler/AuraCompiler.git
cd AuraCompiler
pip install -r requirements.txt
```

Prerequisites (Linux):
```bash
# Debian/Ubuntu
sudo apt install binutils libc6-dev

# Fedora/RHEL
sudo dnf install binutils glibc-devel
```

## Usage

```bash
# Compile to executable
./pycc.py input.c -o output

# Compile to object file
./pycc.py -c input.c -o input.o

# Link object file to executable (CMake workflow)
./pycc.py input.o -o output

# Compile multiple files
./pycc.py a.c b.c -o output -lm

# Compile to assembly
./pycc.py -S input.c -o output.s

# Preprocess only
./pycc.py -E input.c

# Build shared library
./pycc.py -shared -o libfoo.so foo.o -Wl,-soname,libfoo.so.1

# Verbose output
./pycc.py -v input.c -o output
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PYCC_AS` | `as` | Override assembler path |
| `PYCC_LD` | `ld` | Override linker path |

## API Usage

```python
from pycc.compiler import Compiler

compiler = Compiler(optimize=True, use_system_cpp=True)
result = compiler.compile_file("example.c", "example")
if result.success:
    print("Done:", result.output_file)
else:
    for error in result.errors:
        print("Error:", error)
```

## Testing

```bash
# Run all tests
python -m pytest tests/ -q

# Run without property-based tests (faster)
python -m pytest tests/ -q -p no:hypothesis

# Run a specific test
python -m pytest tests/test_integration.py -v
```

## Known Limitations

- Not a full C89 implementation (work in progress)
- No multi-dimensional VLA support
- Optimizer is minimal (constant folding, peephole)
- Single-target: x86-64 Linux only
- See `docs/NEXT_PLAN.md` for planned architectural improvements

## Documentation

- [Architecture](docs/ARCHITECTURE.md) — compiler pipeline and module design
- [C89 Roadmap](docs/C89_ROADMAP.md) — language feature implementation status
- [Next Plan](docs/NEXT_PLAN.md) — planned refactoring (IR restructuring, computed goto, etc.)
- [Feature Tracker](docs/FEATURE_TRACKER.md) — detailed feature status

## References

- "Compilers: Principles, Techniques, and Tools" (Dragon Book)
- "Engineering a Compiler" by Cooper & Torczon
- C89/ANSI C Standard (ISO/IEC 9899:1990)

## License

MIT License — see [LICENSE](LICENSE) for details.

## Author

Zhang Ji Peng (onecoolx@gmail.com)
