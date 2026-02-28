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


def test_ptrdiff_equality_to_int(tmp_path):
    code = r'''
int main(){
    int a[4];
    int *p = a;
    int *q = a + 3;
    return ((q - p) == 3) ? 0 : 1;
}
'''.lstrip()
    assert _compile_and_run(tmp_path, code) == 0


def test_ptrdiff_relational_to_int(tmp_path):
    code = r'''
int main(){
    int a[4];
    int *p = a;
    int *q = a + 3;
    int d = q - p;
    return (d > 2) ? 0 : 1;
}
'''.lstrip()
    assert _compile_and_run(tmp_path, code) == 0


def test_ptrdiff_relational_expression_to_int(tmp_path):
    code = r'''
int main(){
    int a[4];
    int *p = a;
    int *q = a + 2;
    return ((q - p) < 3) ? 0 : 1;
}
'''.lstrip()
    assert _compile_and_run(tmp_path, code) == 0
