"""Property tests: stringize correctness (Property 17)."""
import pytest
from pycc.compiler import Compiler


def _preprocess(tmp_path, code: str) -> str:
    c_path = tmp_path / "t.c"
    c_path.write_text(code)
    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(tmp_path / "t"), preprocess_only=True)
    return res.assembly or ""


def test_stringize_basic(tmp_path):
    code = '#define STR(x) #x\nchar *s = STR(hello);\n'
    out = _preprocess(tmp_path, code)
    assert '"hello"' in out


def test_stringize_whitespace_normalization(tmp_path):
    code = '#define STR(x) #x\nchar *s = STR(a   b   c);\n'
    out = _preprocess(tmp_path, code)
    assert '"a b c"' in out
