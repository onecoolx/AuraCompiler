from pycc.compiler import Compiler


def test_register_parameter_is_rejected(tmp_path):
    code = r'''
int f(register int x){ return x; }
int main(){ return f(3); }
'''.lstrip()

    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)

    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(out_path))
    assert not res.success
