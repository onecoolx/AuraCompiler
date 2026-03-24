from __future__ import annotations

from pathlib import Path

from pycc.compiler import Compiler


def _compile(tmp_path: Path, c_src: str):
    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(c_src)
    comp = Compiler(optimize=False)
    return comp.compile_file(str(c_path), str(out_path))


def test_excess_array_initializer_elements_is_error(tmp_path: Path) -> None:
    code = r"""
int main(void){
  int a[2] = {1,2,3};
  return a[0];
}
""".lstrip()
    res = _compile(tmp_path, code)
    assert not res.success
    assert any("excess" in e.lower() or "too many" in e.lower() for e in (res.errors or []))


def test_excess_array_initializer_nested_is_error(tmp_path: Path) -> None:
    code = r"""
int main(void){
  int a[2][2] = { {1,2}, {3,4}, {5,6} };
  return 0;
}
""".lstrip()
    res = _compile(tmp_path, code)
    assert not res.success
