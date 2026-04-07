"""Property tests: macro expansion token boundary preservation (Property 14)."""
import pytest
from pycc.compiler import Compiler


def _preprocess(tmp_path, code: str) -> str:
    c_path = tmp_path / "t.c"
    c_path.write_text(code)
    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(tmp_path / "t"), preprocess_only=True)
    return res.assembly or ""


def test_object_macro_preserves_token_boundary(tmp_path):
    code = "#define X 1 + 2\nint a = X;\n"
    out = _preprocess(tmp_path, code)
    assert "1 + 2" in out or "1+2" in out


def test_function_macro_preserves_token_boundary(tmp_path):
    code = "#define ADD(a, b) a + b\nint x = ADD(1, 2);\n"
    out = _preprocess(tmp_path, code)
    assert "1 + 2" in out or "1+2" in out
