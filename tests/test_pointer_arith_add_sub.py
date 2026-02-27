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


def test_pointer_addition_scales_by_element_size(tmp_path):
    code = r'''
int main(){
    int a[4];
    int *p = a;
    int *q = p + 2;
    return (q - p) == 2 ? 0 : 1;
}
'''.lstrip()
    assert _compile_and_run(tmp_path, code) == 0


def test_pointer_subtraction_scales_by_element_size(tmp_path):
    code = r'''
int main(){
    int a[4];
    int *p = a + 3;
    int *q = p - 1;
    return (p - q) == 1 ? 0 : 1;
}
'''.lstrip()
    assert _compile_and_run(tmp_path, code) == 0
