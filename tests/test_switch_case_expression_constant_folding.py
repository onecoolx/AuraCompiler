from pycc.compiler import Compiler


def test_switch_case_expression_is_constant_expression(tmp_path):
    # C89: case labels are integral constant expressions.
    code = r'''
int main(){
    int x = 2;
    switch (x) {
        case 1 + 1:
            return 7;
        default:
            return 9;
    }
}
'''.lstrip()

    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)

    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(out_path))
    assert res.success, "compile failed: " + "\n".join(res.errors)
