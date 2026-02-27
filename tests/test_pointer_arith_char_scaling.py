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


def test_char_pointer_addition_scales_by_1(tmp_path):
    code = r'''
int main(){
    char a[4];
    char *p = a;
    char *q = p + 2;
    return (q - p) == 2 ? 0 : 1;
}
'''.lstrip()
    assert _compile_and_run(tmp_path, code) == 0


def test_char_pointer_compound_add_assign_scales_by_1(tmp_path):
    code = r'''
int main(){
    char a[4];
    char *p = a;
    p += 3;
    return (p - a) == 3 ? 0 : 1;
}
'''.lstrip()
    assert _compile_and_run(tmp_path, code) == 0
