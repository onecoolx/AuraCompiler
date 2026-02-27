import subprocess

from pycc.compiler import Compiler


def _compile_and_run(tmp_path, code: str) -> int:
    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)

    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(out_path))
    assert res.success, "compile failed: " + "\n".join(res.errors)

    p = subprocess.run([str(out_path)], check=False)
    return p.returncode


def test_switch_case_ternary_constant_expression(tmp_path):
    code = r'''
int main(){
    int x = 2;
    int y = 0;
    switch (x) {
        case (0 ? 1 : 2):
            y = 7;
            break;
        default:
            y = 9;
            break;
    }
    return y;
}
'''.lstrip()
    assert _compile_and_run(tmp_path, code) == 7
