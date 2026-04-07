"""Property tests: #line updates logical position (Property 21)."""
import pytest
from pycc.compiler import Compiler


def _preprocess(tmp_path, code: str) -> str:
    c_path = tmp_path / "t.c"
    c_path.write_text(code)
    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(tmp_path / "t"), preprocess_only=True)
    return res.assembly or ""


def test_line_directive_updates_line_macro(tmp_path):
    code = '#line 100 "test.c"\nint line = __LINE__;\n'
    out = _preprocess(tmp_path, code)
    assert "101" in out or "100" in out  # __LINE__ should reflect updated line


def test_line_directive_updates_file_macro(tmp_path):
    code = '#line 1 "myfile.c"\nchar *f = __FILE__;\n'
    out = _preprocess(tmp_path, code)
    assert "myfile.c" in out
