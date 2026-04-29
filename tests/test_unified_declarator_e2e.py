"""End-to-end tests for new syntax forms enabled by the unified declarator parser.

Validates Requirements 4.1, 4.2, 4.3:
- 4.1: Parenthesized function names: int (func)(int x)
- 4.2: typedef arrays: typedef int arr_t[23]
- 4.3: Complex nested declarators: int (*(*fp)(int))[10]
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from pycc.compiler import Compiler
from pycc.lexer import Lexer
from pycc.parser import Parser


def _compile_and_run(tmp_path: Path, code: str) -> str:
    """Compile C code, run the binary, return stdout."""
    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)

    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(out_path))
    assert res.success, "compile failed: " + "\n".join(res.errors)

    p = subprocess.run(
        [str(out_path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, timeout=10,
    )
    assert p.returncode == 0, f"runtime error (rc={p.returncode}): {p.stderr}"
    return p.stdout.strip()


def _compile_and_get_rc(tmp_path: Path, code: str) -> int:
    """Compile C code, run the binary, return exit code."""
    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)

    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(out_path))
    assert res.success, "compile failed: " + "\n".join(res.errors)

    p = subprocess.run([str(out_path)], check=False, timeout=10)
    return p.returncode


def _parse_only(code: str) -> bool:
    """Parse C code and return True if parsing succeeds."""
    tokens = Lexer(code).tokenize()
    try:
        ast = Parser(tokens).parse()
        return ast is not None
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Requirement 4.1: Parenthesized function names — int (func)(int x)
# This pattern is used by Lua 5.5 to prevent macro expansion.
# ---------------------------------------------------------------------------

class TestParenthesizedFunctionNames:
    """Parenthesized function names: int (func)(int x) { ... }"""

    def test_paren_func_parse(self):
        """int (func)(int x) should parse as a valid function definition."""
        code = "int (add)(int x, int y) { return x + y; }\nint main(void) { return 0; }\n"
        assert _parse_only(code)

    def test_paren_func_compile_and_run(self, tmp_path: Path):
        """Parenthesized function name compiles and runs correctly."""
        code = (
            'extern int printf(const char *, ...);\n'
            'int (add)(int a, int b) {\n'
            '    return a + b;\n'
            '}\n'
            'int main(void) {\n'
            '    printf("%d\\n", add(17, 25));\n'
            '    return 0;\n'
            '}\n'
        )
        assert _compile_and_run(tmp_path, code) == "42"

    def test_paren_func_void_return(self, tmp_path: Path):
        """Parenthesized function name with void return type."""
        code = (
            'extern int printf(const char *, ...);\n'
            'int g;\n'
            'void (set_g)(int val) {\n'
            '    g = val;\n'
            '}\n'
            'int main(void) {\n'
            '    set_g(99);\n'
            '    printf("%d\\n", g);\n'
            '    return 0;\n'
            '}\n'
        )
        assert _compile_and_run(tmp_path, code) == "99"

    def test_paren_func_pointer_return(self, tmp_path: Path):
        """Parenthesized function name returning a pointer."""
        code = (
            'extern int printf(const char *, ...);\n'
            'int val = 77;\n'
            'int *(get_ptr)(void) {\n'
            '    return &val;\n'
            '}\n'
            'int main(void) {\n'
            '    int *p = get_ptr();\n'
            '    printf("%d\\n", *p);\n'
            '    return 0;\n'
            '}\n'
        )
        assert _compile_and_run(tmp_path, code) == "77"

    def test_paren_func_multiple_definitions(self, tmp_path: Path):
        """Multiple parenthesized function definitions in one file."""
        code = (
            'extern int printf(const char *, ...);\n'
            'int (square)(int x) { return x * x; }\n'
            'int (cube)(int x) { return x * x * x; }\n'
            'int main(void) {\n'
            '    printf("%d %d\\n", square(3), cube(2));\n'
            '    return 0;\n'
            '}\n'
        )
        assert _compile_and_run(tmp_path, code) == "9 8"

    def test_paren_func_call_from_paren_func(self, tmp_path: Path):
        """Parenthesized function calling another parenthesized function."""
        code = (
            'extern int printf(const char *, ...);\n'
            'int (inc)(int x) { return x + 1; }\n'
            'int (double_inc)(int x) { return inc(inc(x)); }\n'
            'int main(void) {\n'
            '    printf("%d\\n", double_inc(40));\n'
            '    return 0;\n'
            '}\n'
        )
        assert _compile_and_run(tmp_path, code) == "42"


# ---------------------------------------------------------------------------
# Requirement 4.2: typedef arrays — typedef int arr_t[23]
# ---------------------------------------------------------------------------

class TestTypedefArrays:
    """typedef arrays: typedef int arr_t[N] — consolidate existing ad-hoc fix."""

    def test_typedef_array_basic_compile_run(self, tmp_path: Path):
        """Basic typedef array declaration, assignment, and access."""
        code = (
            'extern int printf(const char *, ...);\n'
            'typedef int vec3_t[3];\n'
            'int main(void) {\n'
            '    vec3_t v;\n'
            '    v[0] = 10; v[1] = 20; v[2] = 30;\n'
            '    printf("%d %d %d\\n", v[0], v[1], v[2]);\n'
            '    return 0;\n'
            '}\n'
        )
        assert _compile_and_run(tmp_path, code) == "10 20 30"

    def test_typedef_array_passed_to_pointer_param(self, tmp_path: Path):
        """typedef array variable passed to a function taking int pointer."""
        code = (
            'extern int printf(const char *, ...);\n'
            'typedef int arr4_t[4];\n'
            'int sum(int *a, int n) {\n'
            '    int s = 0;\n'
            '    int i;\n'
            '    for (i = 0; i < n; i++) s = s + a[i];\n'
            '    return s;\n'
            '}\n'
            'int main(void) {\n'
            '    arr4_t x;\n'
            '    x[0] = 1; x[1] = 2; x[2] = 3; x[3] = 4;\n'
            '    printf("%d\\n", sum(x, 4));\n'
            '    return 0;\n'
            '}\n'
        )
        assert _compile_and_run(tmp_path, code) == "10"

    def test_typedef_array_in_struct_parse(self):
        """typedef array used as a struct member should parse correctly.

        Note: runtime execution of struct-member array access has a
        pre-existing codegen bug (affects both typedef and plain arrays).
        This test validates the parser handles the declaration correctly.
        """
        code = (
            'typedef int pair_t[2];\n'
            'struct point { pair_t coords; };\n'
            'int main(void) { return 0; }\n'
        )
        assert _parse_only(code)

    def test_typedef_array_multidim(self, tmp_path: Path):
        """Multi-dimensional typedef array."""
        code = (
            'extern int printf(const char *, ...);\n'
            'typedef int mat2x2_t[2][2];\n'
            'int main(void) {\n'
            '    mat2x2_t m;\n'
            '    m[0][0] = 1; m[0][1] = 2;\n'
            '    m[1][0] = 3; m[1][1] = 4;\n'
            '    printf("%d %d %d %d\\n", m[0][0], m[0][1], m[1][0], m[1][1]);\n'
            '    return 0;\n'
            '}\n'
        )
        assert _compile_and_run(tmp_path, code) == "1 2 3 4"


# ---------------------------------------------------------------------------
# Requirement 4.3: Complex nested declarators — int (*(*fp)(int))[10]
# ---------------------------------------------------------------------------

class TestComplexNestedDeclarators:
    """Complex nested declarators: parsing verification."""

    def test_ptr_to_fn_returning_ptr_to_array_parse(self):
        """int (*(*fp)(int))[10] should parse at global scope."""
        code = "int (*(*fp)(int))[10];\nint main(void) { return 0; }\n"
        assert _parse_only(code)

    def test_ptr_to_fn_returning_ptr_to_array_local_parse(self):
        """int (*(*fp)(int))[10] should parse at local scope."""
        code = "int main(void) { int (*(*fp)(int))[10]; return 0; }\n"
        assert _parse_only(code)

    def test_fn_returning_fnptr_parse(self):
        """int (*f(int))(double) — function returning function pointer."""
        code = "int (*f(int a))(double b);\nint main(void) { return 0; }\n"
        assert _parse_only(code)

    def test_double_ptr_fnptr_parse(self):
        """int (**fp)(int) — pointer to pointer to function."""
        code = "int (**fp)(int);\nint main(void) { return 0; }\n"
        assert _parse_only(code)

    def test_ptr_to_array_parse(self):
        """int (*p)[10] — pointer to array of 10 ints."""
        code = "int (*p)[10];\nint main(void) { return 0; }\n"
        assert _parse_only(code)

    def test_nested_declarator_ast_structure(self):
        """Verify AST structure for int (*(*fp)(int))[10]."""
        code = "int (*(*fp)(int))[10];"
        tokens = Lexer(code).tokenize()
        p = Parser(tokens)
        info = p._parse_type_specifier()
        decl_info = p._parse_declarator()
        # Name should be fp
        assert decl_info.name == "fp"
        # Should be a function declarator (has parameter list)
        assert decl_info.is_function is True
        # Should have array dimensions from the outer [10]
        assert 10 in decl_info.array_dims
        # Should have pointer levels (inner * and outer *)
        assert decl_info.pointer_level >= 2
