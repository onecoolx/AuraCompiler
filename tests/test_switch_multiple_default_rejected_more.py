from pycc.compiler import Compiler


def test_switch_multiple_default_is_rejected(tmp_path):
    code = r'''
int main(){
    int x = 0;
    switch (x) {
        default:
            return 1;
        default:
            return 2;
    }
}
'''.lstrip()

    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)

    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(out_path))
    assert not res.success
