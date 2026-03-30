import pytest

from pycc.compiler import Compiler


def _compile(tmp_path, code: str):
    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)

    comp = Compiler(optimize=False)
    return comp.compile_file(str(c_path), str(out_path))


def test_pointer_assign_from_int_rejected(tmp_path):
    # C89 constraint: assigning an int (non-zero) to a pointer without cast is invalid.
    code = r"""
int main(void) {
  int *p;
  p = 1;
  return 0;
}
""".lstrip()
    res = _compile(tmp_path, code)
    assert not res.success
