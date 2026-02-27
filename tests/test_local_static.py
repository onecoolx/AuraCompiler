from pycc.compiler import Compiler


def test_local_static_without_initializer_is_error(tmp_path):
    # Feature A (subset): function-scope `static` objects are supported.
    code = r'''
int main(){
  static int x;
  x = 41;
  return x + 1;
}
'''.lstrip()

    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)

    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(out_path))
    assert res.success


def test_local_static_with_initializer_is_error(tmp_path):
    # Feature A (subset): function-scope `static` objects are supported.
    code = r'''
int main(){
  static int x = 1;
  return x;
}
'''.lstrip()

    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)

    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(out_path))
    assert res.success
