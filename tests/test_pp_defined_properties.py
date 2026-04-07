"""Property tests: defined after macro expansion (Property 20)."""
import pytest
from pycc.compiler import Compiler


def _preprocess(tmp_path, code: str) -> str:
    c_path = tmp_path / "t.c"
    c_path.write_text(code)
    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(tmp_path / "t"), preprocess_only=True)
    return res.assembly or ""


def test_defined_with_defined_macro(tmp_path):
    code = "#define FOO 1\n#if defined(FOO)\nint ok;\n#endif\n"
    out = _preprocess(tmp_path, code)
    assert "int ok" in out


def test_defined_with_undefined_macro(tmp_path):
    code = "#if defined(BAR)\nint bad;\n#else\nint ok;\n#endif\n"
    out = _preprocess(tmp_path, code)
    assert "int ok" in out
    assert "int bad" not in out
