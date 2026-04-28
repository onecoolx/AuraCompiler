"""Tests for typedef array declarations (e.g. typedef int arr_t[23]).

Verifies that the parser, semantics, and compilation pipeline correctly
handle typedef names that include array dimensions — a pattern commonly
found in glibc system headers (e.g. gregset_t, __jmp_buf).
"""

import subprocess
from pathlib import Path

import pytest

from pycc.compiler import Compiler
from pycc.parser import Parser
from pycc.lexer import Lexer


def _compile_and_run(tmp_path: Path, code: str) -> str:
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


class TestTypedefArrayParsing:
    """Parser accepts typedef with array suffix."""

    def test_simple_typedef_array(self):
        code = "typedef int arr_t[10];"
        tokens = Lexer(code).tokenize()
        ast = Parser(tokens).parse()
        assert ast is not None

    def test_typedef_array_of_typedef(self):
        code = "typedef long long int greg_t;\ntypedef greg_t gregset_t[23];"
        tokens = Lexer(code).tokenize()
        ast = Parser(tokens).parse()
        assert ast is not None

    def test_typedef_multidim_array(self):
        code = "typedef int matrix_t[3][4];"
        tokens = Lexer(code).tokenize()
        ast = Parser(tokens).parse()
        assert ast is not None

    def test_typedef_array_unsized(self):
        code = "typedef int flex_t[];"
        tokens = Lexer(code).tokenize()
        ast = Parser(tokens).parse()
        assert ast is not None


class TestTypedefArrayCompileAndRun:
    """End-to-end: typedef array variables compile and run correctly."""

    def test_1d_array_typedef(self, tmp_path):
        code = (
            'extern int printf(const char *, ...);\n'
            'typedef int arr5_t[5];\n'
            'int main(void) {\n'
            '    arr5_t a;\n'
            '    a[0] = 10; a[1] = 20; a[2] = 30; a[3] = 40; a[4] = 50;\n'
            '    printf("%d %d %d\\n", a[0], a[2], a[4]);\n'
            '    return 0;\n'
            '}\n'
        )
        assert _compile_and_run(tmp_path, code) == "10 30 50"

    def test_typedef_of_typedef_array(self, tmp_path):
        code = (
            'extern int printf(const char *, ...);\n'
            'typedef int myint;\n'
            'typedef myint myarr_t[4];\n'
            'int main(void) {\n'
            '    myarr_t g;\n'
            '    g[0] = 100; g[1] = 200; g[2] = 300; g[3] = 400;\n'
            '    printf("%d %d\\n", g[0], g[3]);\n'
            '    return 0;\n'
            '}\n'
        )
        assert _compile_and_run(tmp_path, code) == "100 400"

    def test_glibc_signal_pattern(self, tmp_path):
        """Pattern from glibc <signal.h>: typedef + struct with array member."""
        code = (
            'extern int printf(const char *, ...);\n'
            'typedef unsigned int uint32_t;\n'
            'typedef long long int greg_t;\n'
            'typedef greg_t gregset_t[23];\n'
            'struct _libc_fpxreg {\n'
            '    unsigned short int significand[4];\n'
            '    unsigned short int exponent;\n'
            '};\n'
            'struct _libc_xmmreg {\n'
            '    uint32_t element[4];\n'
            '};\n'
            'int main(void) {\n'
            '    gregset_t g;\n'
            '    g[0] = 42;\n'
            '    printf("%d\\n", (int)g[0]);\n'
            '    return 0;\n'
            '}\n'
        )
        assert _compile_and_run(tmp_path, code) == "42"
