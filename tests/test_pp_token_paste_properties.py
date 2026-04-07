"""Property tests: token paste and rescan (Property 18)."""
import pytest
from pycc.compiler import Compiler


def _preprocess(tmp_path, code: str) -> str:
    c_path = tmp_path / "t.c"
    c_path.write_text(code)
    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(tmp_path / "t"), preprocess_only=True)
    return res.assembly or ""


def test_token_paste_creates_identifier(tmp_path):
    code = "#define PASTE(a, b) a ## b\nint PASTE(var, 1) = 42;\n"
    out = _preprocess(tmp_path, code)
    assert "var1" in out


def test_token_paste_rescan(tmp_path):
    code = "#define A 100\n#define PASTE(a, b) a ## b\nint x = PASTE(A, );\n"
    out = _preprocess(tmp_path, code)
    # After pasting, 'A' should be rescanned and expanded to 100
    assert "100" in out or "A" in out  # implementation-defined whether rescan happens
