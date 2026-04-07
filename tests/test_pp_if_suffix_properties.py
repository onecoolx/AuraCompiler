"""Property tests: #if integer suffix handling (Property 19)."""
import pytest
from pycc.compiler import Compiler


def _preprocess(tmp_path, code: str) -> str:
    c_path = tmp_path / "t.c"
    c_path.write_text(code)
    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(tmp_path / "t"), preprocess_only=True)
    return res.assembly or ""


def test_if_unsigned_suffix(tmp_path):
    code = "#if 1U\nint ok;\n#endif\n"
    out = _preprocess(tmp_path, code)
    assert "int ok" in out


def test_if_long_suffix(tmp_path):
    code = "#if 1L\nint ok;\n#endif\n"
    out = _preprocess(tmp_path, code)
    assert "int ok" in out


def test_if_unsigned_long_suffix(tmp_path):
    code = "#if 1UL\nint ok;\n#endif\n"
    out = _preprocess(tmp_path, code)
    assert "int ok" in out
