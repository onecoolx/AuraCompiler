"""Property tests: function macro argument expansion order (Property 16)."""
import pytest
from pycc.compiler import Compiler


def _preprocess(tmp_path, code: str) -> str:
    c_path = tmp_path / "t.c"
    c_path.write_text(code)
    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(tmp_path / "t"), preprocess_only=True)
    return res.assembly or ""


def test_args_expanded_before_substitution(tmp_path):
    """Arguments are expanded before substitution into replacement list."""
    code = "#define Y 10\n#define F(x) x + x\nint a = F(Y);\n"
    out = _preprocess(tmp_path, code)
    assert "10 + 10" in out or "10+10" in out
