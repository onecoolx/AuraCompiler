from pycc.compiler import Compiler


def test_const_local_assignment_is_error(tmp_path):
    code = r'''
int main(){
  const int x = 1;
  x = 2;
  return 0;
}
'''.lstrip()
    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)

    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(out_path))
    assert not res.success


def test_const_local_init_ok(tmp_path):
    code = r'''
int main(){
  const int x = 41;
  return x + 1;
}
'''.lstrip()
    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)

    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(out_path))
    assert res.success


def test_const_local_compound_assignment_is_error(tmp_path):
    code = r'''
int main(){
  const int x = 1;
  x += 1;
  return 0;
}
'''.lstrip()
    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)

    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(out_path))
    assert not res.success
