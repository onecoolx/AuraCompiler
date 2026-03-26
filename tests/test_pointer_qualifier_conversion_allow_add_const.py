from __future__ import annotations

from pathlib import Path

from pycc.compiler import Compiler


def _compile(tmp_path: Path, code: str):
    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)
    comp = Compiler(optimize=False)
    return comp.compile_file(str(c_path), str(out_path))


def test_allow_add_const_in_pointer_chain_assignment(tmp_path: Path) -> None:
    code = r"""
int main(void){
  int x = 1;
  int *p = &x;
    const int *cp;  /* pointer is not const; pointee is const */
  cp = p;
  return *cp == 1 ? 0 : 1;
}
""".lstrip()
    res = _compile(tmp_path, code)
    assert res.success, "unexpected failure: " + "\n".join(res.errors)
