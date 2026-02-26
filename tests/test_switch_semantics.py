import pytest

from pycc.compiler import Compiler


def _compile(tmp_path, code: str):
    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)

    comp = Compiler(optimize=False)
    return comp.compile_file(str(c_path), str(out_path))


def test_switch_reject_duplicate_case_value(tmp_path):
    code = r"""
int main(){
  int x = 1;
  switch(x){
    case 1: return 10;
    case 1: return 20;
    default: return 0;
  }
}
""".lstrip()
    res = _compile(tmp_path, code)
    assert not res.success


def test_switch_reject_multiple_default_labels(tmp_path):
    code = r"""
int main(){
  int x = 1;
  switch(x){
    default: x = 2;
    default: return 0;
  }
  return x;
}
""".lstrip()
    res = _compile(tmp_path, code)
    assert not res.success
