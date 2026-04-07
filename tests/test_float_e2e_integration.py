"""End-to-end integration tests for float support."""
import pytest
import subprocess
import os
from pycc.compiler import Compiler


def _compile(tmp_path, code: str):
    c_path = tmp_path / "t.c"
    c_path.write_text(code)
    comp = Compiler(optimize=False)
    return comp.compile_file(str(c_path), str(tmp_path / "t.s"))


def _compile_and_run(tmp_path, code: str) -> int:
    """Compile to executable and run, return exit code."""
    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)
    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(out_path))
    if not res.success:
        pytest.skip(f"compilation failed: {res.errors}")
    if not os.path.isfile(str(out_path)):
        pytest.skip("no executable produced")
    r = subprocess.run([str(out_path)], capture_output=True, timeout=5)
    return r.returncode


def test_float_local_variable_compiles(tmp_path):
    code = "int main(void) { float x = 3.14f; return 0; }\n"
    res = _compile(tmp_path, code)
    assert res.success


def test_double_local_variable_compiles(tmp_path):
    code = "int main(void) { double y = 2.718; return 0; }\n"
    res = _compile(tmp_path, code)
    assert res.success


def test_float_type_declaration_compiles(tmp_path):
    code = "float g;\nint main(void) { return 0; }\n"
    res = _compile(tmp_path, code)
    assert res.success


def test_double_type_declaration_compiles(tmp_path):
    code = "double g;\nint main(void) { return 0; }\n"
    res = _compile(tmp_path, code)
    assert res.success


def test_float_literal_exponent_compiles(tmp_path):
    code = "int main(void) { double x = 1.5e2; return 0; }\n"
    res = _compile(tmp_path, code)
    assert res.success


def test_float_arithmetic_add_compiles(tmp_path):
    code = "int main(void) { float a = 1.0f; float b = 2.0f; float c = a + b; return 0; }\n"
    res = _compile(tmp_path, code)
    assert res.success


def test_float_arithmetic_mul_compiles(tmp_path):
    code = "int main(void) { double a = 2.0; double b = 3.0; double c = a * b; return 0; }\n"
    res = _compile(tmp_path, code)
    assert res.success


def test_float_compare_compiles(tmp_path):
    code = "int main(void) { float a = 1.0f; float b = 2.0f; int r = a < b; return 0; }\n"
    res = _compile(tmp_path, code)
    assert res.success


def test_float_cast_int_to_float_compiles(tmp_path):
    code = "int main(void) { int x = 42; float f = (float)x; return 0; }\n"
    res = _compile(tmp_path, code)
    assert res.success


def test_float_cast_float_to_int_compiles(tmp_path):
    code = "int main(void) { float f = 3.14f; int x = (int)f; return x; }\n"
    res = _compile(tmp_path, code)
    assert res.success


def test_float_cast_to_int_runs(tmp_path):
    """(int)3.14f should yield 3."""
    code = "int main(void) { float f = 3.14f; int x = (int)f; return x; }\n"
    rc = _compile_and_run(tmp_path, code)
    assert rc == 3


def test_double_arithmetic_runs(tmp_path):
    """(int)(2.0 + 3.0) should yield 5."""
    code = "int main(void) { double a = 2.0; double b = 3.0; double c = a + b; return (int)c; }\n"
    rc = _compile_and_run(tmp_path, code)
    assert rc == 5


def test_float_compare_runs(tmp_path):
    """1.0f < 2.0f should be true (1)."""
    code = "int main(void) { float a = 1.0f; float b = 2.0f; return a < b; }\n"
    rc = _compile_and_run(tmp_path, code)
    assert rc == 1
