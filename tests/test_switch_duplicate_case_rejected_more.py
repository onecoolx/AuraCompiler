from pycc.compiler import Compiler


def test_switch_duplicate_case_is_rejected(tmp_path):
    code = r'''
int main(){
    int x = 1;
    switch (x) {
        case 1:
            return 10;
        case 1:
            return 20;
        default:
            return 30;
    }
}
'''.lstrip()

    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)

    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(out_path))
    assert not res.success
