from pycc.compiler import Compiler


def test_assignment_through_pointer_to_const_is_error(tmp_path):
    # Feature B (subset): reject writes through pointers to const.
    code = r'''
int main(){
  const int x = 1;
  int * const p = &x;
  *p = 2;
  return 0;
}
'''.lstrip()

    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)

    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(out_path))
    assert not res.success


def test_assignment_through_pointer_to_nonconst_ok(tmp_path):
    code = r'''
int main(){
  int x = 1;
  int *p = &x;
  *p = 2;
  return x;
}
'''.lstrip()

    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)

    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(out_path))
    assert res.success
