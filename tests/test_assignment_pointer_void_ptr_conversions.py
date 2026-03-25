from pathlib import Path

from pycc.compiler import Compiler


def _compile(tmp_path: Path, code: str):
    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)
    comp = Compiler(optimize=False)
    return comp.compile_file(str(c_path), str(out_path))


def test_allow_assign_typed_ptr_to_void_ptr(tmp_path: Path):
    code = r"""
int main(void){
  int x = 0;
  void *p;
  p = &x;
  return p ? 0 : 1;
}
""".lstrip()
    res = _compile(tmp_path, code)
    assert res.success, "unexpected failure: " + "\n".join(res.errors)


def test_allow_assign_void_ptr_to_typed_ptr(tmp_path: Path):
    code = r"""
int main(void){
  int x = 0;
  void *p = &x;
  int *q;
  q = p;
  return q ? 0 : 1;
}
""".lstrip()
    res = _compile(tmp_path, code)
    assert res.success, "unexpected failure: " + "\n".join(res.errors)
