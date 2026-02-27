from pycc.compiler import Compiler


def _compile_and_run(tmp_path, code: str) -> int:
    import subprocess

    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)

    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(out_path))
    assert res.success, "compile failed: " + "\n".join(res.errors)

    p = subprocess.run([str(out_path)], check=False)
    return p.returncode


def test_comma_operator_evaluates_left_to_right(tmp_path):
    code = r'''
int main(){
    int x = 0;
    int y = (x = 1, x + 2);
    return y;
}
'''.lstrip()
    assert _compile_and_run(tmp_path, code) == 3


def test_comma_operator_in_while_condition(tmp_path):
    code = r'''
int main(){
    int x = 0;
    int n = 0;
    while (x < 3, x = x + 1, x < 3) {
        n = n + 1;
    }
    return n;
}
'''.lstrip()
    assert _compile_and_run(tmp_path, code) == 2
