"""Property tests: const object modification rejection (Property 6)."""
import pytest
from pycc.compiler import Compiler


def _compile(tmp_path, code: str):
    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)
    comp = Compiler(optimize=False)
    return comp.compile_file(str(c_path), str(out_path))


def test_const_int_assign_rejected(tmp_path):
    code = "int main(void) { const int x = 1; x = 2; return 0; }\n"
    res = _compile(tmp_path, code)
    assert not res.success
    assert any("const" in e.lower() or "modifiable" in e.lower() for e in res.errors)


def test_const_int_compound_assign_rejected(tmp_path):
    code = "int main(void) { const int x = 1; x += 2; return 0; }\n"
    res = _compile(tmp_path, code)
    assert not res.success
    assert any("const" in e.lower() or "modifiable" in e.lower() for e in res.errors)


def test_const_array_element_assign_rejected(tmp_path):
    code = "int main(void) { const int a[2] = {1, 2}; a[0] = 3; return 0; }\n"
    res = _compile(tmp_path, code)
    assert not res.success


def test_nonconst_assign_allowed(tmp_path):
    code = "int main(void) { int x = 1; x = 2; return x; }\n"
    res = _compile(tmp_path, code)
    assert res.success
