from __future__ import annotations

from pycc.compiler import Compiler


def _compile(tmp_path, code: str):
    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)

    comp = Compiler(optimize=False)
    return comp.compile_file(str(c_path), str(out_path))


def test_reject_const_dropping_int_pp_to_const_int_pp(tmp_path):
    # Classic constraint violation: converting T** to const T** is not allowed.
    code = r'''
int main(void){
  int x = 1;
  int *p = &x;
  int **pp = &p;
  const int **cpp = pp;
  (void)cpp;
  return 0;
}
'''.lstrip()
    res = _compile(tmp_path, code)
    assert not res.success


def test_reject_const_dropping_addr_of_int_p_to_const_int_pp(tmp_path):
    # Classic constraint violation: const int **ppc = &pi; where pi is int*.
    code = r'''
int main(void){
  int x = 1;
  int *pi = &x;
  const int **ppc = &pi;
  (void)ppc;
  return 0;
}
'''.lstrip()
    res = _compile(tmp_path, code)
    assert not res.success


def test_reject_write_through_double_pointer_to_const(tmp_path):
    # Writing through **pp should be rejected when ultimate pointee is const.
    code = r'''
int main(void){
  const int x = 1;
  const int *p = &x;
  const int **pp = &p;
  **pp = 2;
  return 0;
}
'''.lstrip()
    res = _compile(tmp_path, code)
    assert not res.success
