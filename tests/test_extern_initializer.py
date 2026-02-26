from pycc.compiler import Compiler


def test_extern_global_with_initializer_is_error(tmp_path):
    code = r'''
extern int g = 1;
int main(){ return 0; }
'''.lstrip()
    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)

    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(out_path))
    assert not res.success


def test_extern_local_with_initializer_is_error(tmp_path):
    code = r'''
int main(){
  extern int x = 1;
  return x;
}
'''.lstrip()
    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)

    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(out_path))
    assert not res.success


def test_extern_declaration_without_initializer_ok(tmp_path):
    code = r'''
extern int g;
int g = 41;
int main(){ return g + 1; }
'''.lstrip()
    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)

    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(out_path))
    assert res.success
