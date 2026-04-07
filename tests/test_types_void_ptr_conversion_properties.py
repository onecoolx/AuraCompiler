"""Property tests: void* implicit conversion (Property 8)."""
import pytest
from pycc.compiler import Compiler


def _compile(tmp_path, code: str):
    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)
    comp = Compiler(optimize=False)
    return comp.compile_file(str(c_path), str(out_path))


def test_void_ptr_from_int_ptr_allowed(tmp_path):
    code = "int main(void) { int x; void *vp = &x; return 0; }\n"
    res = _compile(tmp_path, code)
    assert res.success


def test_int_ptr_from_void_ptr_allowed(tmp_path):
    code = "int main(void) { int x; void *vp = &x; int *ip = vp; return *ip; }\n"
    res = _compile(tmp_path, code)
    assert res.success
