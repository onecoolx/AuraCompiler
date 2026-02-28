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


def test_pointer_inequality_comparison(tmp_path):
    code = r'''
int main(){
    int a[3];
    int *p = a;
    int *q = a + 1;
    return (p != q) ? 0 : 1;
}
'''.lstrip()
    assert _compile_and_run(tmp_path, code) == 0


def test_pointer_relational_comparison_same_array_gt(tmp_path):
    code = r'''
int main(){
    int a[3];
    int *p = a + 2;
    int *q = a;
    return (p > q) ? 0 : 1;
}
'''.lstrip()
    assert _compile_and_run(tmp_path, code) == 0


def test_pointer_relational_comparison_same_array_lte_gte(tmp_path):
    code = r'''
int main(){
    int a[3];
    int *p = a;
    int *q = a;
    int ok = (p <= q) && (p >= q);
    return ok ? 0 : 1;
}
'''.lstrip()
    assert _compile_and_run(tmp_path, code) == 0


def test_pointer_compare_after_cast_to_void_ptr(tmp_path):
    # Ensure casts don't break compare lowering.
    code = r'''
int main(){
    int a[1];
    void *p = (void*)a;
    void *q = (void*)a;
    return (p == q) ? 0 : 1;
}
'''.lstrip()
    assert _compile_and_run(tmp_path, code) == 0
