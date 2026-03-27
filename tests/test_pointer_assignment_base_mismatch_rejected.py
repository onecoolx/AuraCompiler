from __future__ import annotations

from pathlib import Path

from pycc.compiler import Compiler


def _compile(tmp_path: Path, c_src: str):
    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(c_src)

    comp = Compiler(optimize=False)
    return comp.compile_file(str(c_path), str(out_path))


def test_pointer_assignment_base_mismatch_is_error(tmp_path: Path) -> None:
    # C89 constraint (subset): assigning incompatible pointer types should be rejected.
    # Example: char* -> int* without cast.
    code = r"""
int main(void){
  char c = 0;
  char *pc = &c;
  int *pi;
  pi = pc;  /* incompatible pointer types */
  (void)pi;
  return 0;
}
""".lstrip()
    res = _compile(tmp_path, code)
    assert not res.success, "expected failure but succeeded"


def test_pointer_assignment_void_ptr_ok(tmp_path: Path) -> None:
    # void* can convert to/from object pointers (subset) without cast.
    code = r"""
int main(void){
  int x = 1;
  int *pi = &x;
  void *pv = pi;
  int *pi2 = pv;
  return *pi2 == 1 ? 0 : 1;
}
""".lstrip()
    res = _compile(tmp_path, code)
    assert res.success, "unexpected failure: " + "\n".join(res.errors)
