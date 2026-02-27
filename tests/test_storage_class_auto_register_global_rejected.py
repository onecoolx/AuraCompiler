from pycc.compiler import Compiler


def test_global_register_is_rejected(tmp_path):
    code = r'''
register int g;
int main(){ return 0; }
'''.lstrip()

    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)

    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(out_path))
    assert not res.success


def test_global_auto_is_rejected(tmp_path):
    code = r'''
auto int g;
int main(){ return 0; }
'''.lstrip()

    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)

    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(out_path))
    assert not res.success
