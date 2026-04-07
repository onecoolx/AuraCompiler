"""Property tests: incompatible pointer type assignment rejection (Property 9)."""
import pytest
from pycc.compiler import Compiler


def _compile(tmp_path, code: str):
    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)
    comp = Compiler(optimize=False)
    return comp.compile_file(str(c_path), str(out_path))


def test_int_ptr_from_char_ptr_rejected(tmp_path):
    code = "int main(void) { char c; int *p = &c; return *p; }\n"
    res = _compile(tmp_path, code)
    assert not res.success


def test_same_type_ptr_allowed(tmp_path):
    code = "int main(void) { int x; int *p = &x; return *p; }\n"
    res = _compile(tmp_path, code)
    assert res.success
