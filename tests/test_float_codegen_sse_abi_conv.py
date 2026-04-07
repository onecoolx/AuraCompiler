"""Property tests: float codegen SSE (Property 27), SysV ABI (Property 28), type conversion (Property 29)."""
import pytest
from pycc.compiler import Compiler


def _get_asm(tmp_path, code: str) -> str:
    c_path = tmp_path / "t.c"
    c_path.write_text(code)
    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(tmp_path / "t.s"))
    return res.assembly or ""


# Property 27: SSE arithmetic instructions
def test_float_add_emits_addss(tmp_path):
    code = "int main(void) { float a = 1.0f; float b = 2.0f; float c = a + b; return 0; }\n"
    asm = _get_asm(tmp_path, code)
    assert "addss" in asm


def test_double_mul_emits_mulsd(tmp_path):
    code = "int main(void) { double a = 2.0; double b = 3.0; double c = a * b; return 0; }\n"
    asm = _get_asm(tmp_path, code)
    assert "mulsd" in asm


def test_float_div_emits_divss(tmp_path):
    code = "int main(void) { float a = 6.0f; float b = 2.0f; float c = a / b; return 0; }\n"
    asm = _get_asm(tmp_path, code)
    assert "divss" in asm


def test_float_compare_emits_ucomiss(tmp_path):
    code = "int main(void) { float a = 1.0f; float b = 2.0f; int r = a < b; return r; }\n"
    asm = _get_asm(tmp_path, code)
    assert "ucomiss" in asm


def test_double_compare_emits_ucomisd(tmp_path):
    code = "int main(void) { double a = 1.0; double b = 2.0; int r = a > b; return r; }\n"
    asm = _get_asm(tmp_path, code)
    assert "ucomisd" in asm


# Property 29: type conversion instructions
def test_int_to_float_emits_cvtsi2ss(tmp_path):
    code = "int main(void) { int x = 42; float f = (float)x; return 0; }\n"
    asm = _get_asm(tmp_path, code)
    assert "cvtsi2ss" in asm


def test_int_to_double_emits_cvtsi2sd(tmp_path):
    code = "int main(void) { int x = 42; double d = (double)x; return 0; }\n"
    asm = _get_asm(tmp_path, code)
    assert "cvtsi2sd" in asm


def test_float_to_int_emits_cvttss2si(tmp_path):
    code = "int main(void) { float f = 3.14f; int x = (int)f; return x; }\n"
    asm = _get_asm(tmp_path, code)
    assert "cvttss2si" in asm


def test_double_to_int_emits_cvttsd2si(tmp_path):
    code = "int main(void) { double d = 3.14; int x = (int)d; return x; }\n"
    asm = _get_asm(tmp_path, code)
    assert "cvttsd2si" in asm


def test_float_to_double_emits_cvtss2sd(tmp_path):
    code = "int main(void) { float f = 1.0f; double d = (double)f; return 0; }\n"
    asm = _get_asm(tmp_path, code)
    assert "cvtss2sd" in asm
