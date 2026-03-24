from __future__ import annotations
from __future__ import annotations

from pathlib import Path

from pycc.compiler import Compiler


def _compile(tmp_path: Path, c_src: str):
    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(c_src)
    comp = Compiler(optimize=False)
    return comp.compile_file(str(c_path), str(out_path))


def test_excess_struct_initializer_elements_is_error(tmp_path: Path) -> None:
    code = r"""
struct S { int a; };

int main(void){
  struct S s = { 1, 2 };
  return s.a;
}
""".lstrip()
    res = _compile(tmp_path, code)
    assert not res.success
    assert any("excess" in e.lower() or "too many" in e.lower() for e in (res.errors or []))


def test_excess_struct_initializer_nested_member_is_error(tmp_path: Path) -> None:
    # Excess elements for an aggregate member should be rejected.
    code = r"""
struct T { int x; };
struct S { struct T t; };

int main(void){
  struct S s = { { 1, 2 } };
  return s.t.x;
}
""".lstrip()
    res = _compile(tmp_path, code)
    assert not res.success
from pathlib import Path

from pycc.compiler import Compiler


def _compile(tmp_path: Path, c_src: str):
    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(c_src)
    comp = Compiler(optimize=False)
    return comp.compile_file(str(c_path), str(out_path))


def test_excess_struct_initializer_elements_is_error(tmp_path: Path) -> None:
    code = r"""
struct S { int a; };

int main(void){
  struct S s = { 1, 2 };
  return s.a;
}
""".lstrip()
    res = _compile(tmp_path, code)
    assert not res.success
    assert any("excess" in e.lower() or "too many" in e.lower() for e in (res.errors or []))
