import pytest

from pycc.compiler import Compiler


def _compile(tmp_path, code: str):
  c_path = tmp_path / "t.c"
  out_path = tmp_path / "t"
  c_path.write_text(code)

  comp = Compiler(optimize=False)
  return comp.compile_file(str(c_path), str(out_path))


def test_switch_case_value_must_be_ice(tmp_path) -> None:
    src = r"""
int f(int x) {
  int y = 3;
  switch (x) {
    case y:
      return 1;
    default:
      return 0;
  }
}
"""
    res = _compile(tmp_path, src)
    assert not res.success
