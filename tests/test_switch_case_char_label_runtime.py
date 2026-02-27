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


def test_switch_case_char_label_matches(tmp_path):
    code = r'''
int main(){
    int x = 'A';
    int y = 0;
    switch (x) {
        case 'A':
            y = 1;
            break;
        case 'B':
            y = 2;
            break;
        default:
            y = 3;
            break;
    }
    return y;
}
'''.lstrip()
    assert _compile_and_run(tmp_path, code) == 1
