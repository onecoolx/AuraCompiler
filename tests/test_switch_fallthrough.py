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


def test_switch_fallthrough_executes_next_case(tmp_path):
    code = r'''
int main(){
    int x = 1;
    int y = 0;
    switch (x) {
        case 1:
            y = 5;
        case 2:
            y = y + 7;
            break;
        default:
            y = 99;
    }
    return y;
}
'''.lstrip()
    assert _compile_and_run(tmp_path, code) == 12
