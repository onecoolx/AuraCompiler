"""Property tests: float codegen SSE instructions (Property 27)."""
import pytest
from pycc.compiler import Compiler


def _compile_asm(tmp_path, code: str) -> str:
    c_path = tmp_path / "t.c"
    c_path.write_text(code)
    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(tmp_path / "t.s"))
    return res.assembly or ""


def test_float_literal_uses_movss(tmp_path):
    code = "int main(void) { float x = 3.14f; return 0; }\n"
    asm = _compile_asm(tmp_path, code)
    assert "movss" in asm


def test_double_literal_uses_movsd(tmp_path):
    code = "int main(void) { double y = 1.0; return 0; }\n"
    asm = _compile_asm(tmp_path, code)
    assert "movsd" in asm


def test_float_literal_in_rodata(tmp_path):
    code = "int main(void) { float x = 3.14f; return 0; }\n"
    asm = _compile_asm(tmp_path, code)
    assert ".rodata" in asm
    assert ".LF" in asm
