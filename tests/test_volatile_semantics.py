from __future__ import annotations


from pycc.compiler import Compiler


def test_volatile_local_assignment_allowed(tmp_path):
    code = r'''
int main(){
  volatile int x = 1;
  x = 2;
  return x == 2 ? 0 : 1;
}
'''.lstrip()
    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)

    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(out_path))
    assert res.success


def test_volatile_pointer_store_allowed(tmp_path):
    code = r'''
int main(){
  volatile int x = 0;
  volatile int *p = &x;
  *p = 42;
  return x == 42 ? 0 : 1;
}
'''.lstrip()
    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)

    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(out_path))
    assert res.success
