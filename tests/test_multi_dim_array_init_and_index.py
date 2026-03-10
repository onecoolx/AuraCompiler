from pycc.compiler import Compiler


def _compile_and_run(tmp_path, code: str) -> int:
    import subprocess

    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code, encoding="utf-8")

    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(out_path))
    assert res.success, "compile failed: " + "\n".join(res.errors)

    p = subprocess.run([str(out_path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return p.returncode


def test_local_2d_char_array_brace_init_and_index(tmp_path):
    code = r'''
int main(void){
  char a[2][4] = { {1,2,3,4}, {5,6,7,8} };
    return (a[0][0] == 1 && a[0][3] == 4 && a[1][0] == 5 && a[1][2] == 7) ? 0 : 1;
}
'''
    assert _compile_and_run(tmp_path, code) == 0
