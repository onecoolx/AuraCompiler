"""Property tests: pointer qualifier compatibility (Property 7)."""
import pytest
from pycc.compiler import Compiler


def _compile(tmp_path, code: str):
    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)
    comp = Compiler(optimize=False)
    return comp.compile_file(str(c_path), str(out_path))


def test_add_const_to_pointee_allowed(tmp_path):
    """int* -> const int* is allowed."""
    code = "int main(void) { int x; int *p = &x; const int *cp = p; return *cp; }\n"
    res = _compile(tmp_path, code)
    assert res.success


def test_remove_const_from_pointee_rejected(tmp_path):
    """const int* -> int* should be rejected."""
    code = "int main(void) { const int x = 1; const int *cp = &x; int *p = cp; return *p; }\n"
    res = _compile(tmp_path, code)
    assert not res.success
    assert any("const" in e.lower() or "qualifier" in e.lower() for e in res.errors)
