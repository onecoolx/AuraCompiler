"""Property tests: macros not expanded in strings/char literals (Property 15)."""
import pytest
from pycc.compiler import Compiler


def _preprocess(tmp_path, code: str) -> str:
    c_path = tmp_path / "t.c"
    c_path.write_text(code)
    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(tmp_path / "t"), preprocess_only=True)
    return res.assembly or ""


def test_macro_not_expanded_in_string(tmp_path):
    code = '#define X 42\nchar *s = "X";\n'
    out = _preprocess(tmp_path, code)
    assert '"X"' in out


def test_macro_not_expanded_in_char_literal(tmp_path):
    code = "#define A 65\nchar c = 'A';\n"
    out = _preprocess(tmp_path, code)
    assert "'A'" in out
