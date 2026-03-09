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


def test_sizeof_expr_char_variable(tmp_path):
    code = r"""
int main(){
    char c = 1;
    return (sizeof(c) == 1) ? 0 : 1;
}
""".lstrip()
    assert _compile_and_run(tmp_path, code) == 0


def test_sizeof_expr_short_variable(tmp_path):
    code = r"""
int main(){
    short s = 1;
    return (sizeof(s) == 2) ? 0 : 1;
}
""".lstrip()
    assert _compile_and_run(tmp_path, code) == 0


def test_sizeof_expr_pointer_variable(tmp_path):
    code = r"""
int main(){
    int x = 1;
    int* p = &x;
    return (sizeof(p) == 8) ? 0 : 1;
}
""".lstrip()
    assert _compile_and_run(tmp_path, code) == 0


def test_sizeof_expr_deref_pointer(tmp_path):
    code = r"""
int main(){
    int x = 1;
    int* p = &x;
    return (sizeof(*p) == 4) ? 0 : 1;
}
""".lstrip()
    assert _compile_and_run(tmp_path, code) == 0


def test_sizeof_expr_no_side_effect(tmp_path):
    code = r"""
int main(){
    int i = 0;
    /* sizeof operand must not be evaluated; use +1 to avoid relying on ++ parsing */
    (void)sizeof(i + 1);
    return (i == 0) ? 0 : 1;
}
""".lstrip()
    assert _compile_and_run(tmp_path, code) == 0
