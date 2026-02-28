from pycc.compiler import Compiler


def test_reject_equality_compare_ptr_vs_int_nonzero(tmp_path):
    code = r'''
int main(){
    int a[1];
    int *p = a;
    return (p == 1) ? 0 : 1;
}
'''.lstrip()

    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)

    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(out_path))
    assert not res.success
    msg = "\n".join(res.errors).lower()
    assert "pointer" in msg and "==" in msg


def test_allow_equality_compare_ptr_vs_zero(tmp_path):
    # C allows comparison against 0 / null pointer constant.
    code = r'''
int main(){
    int a[1];
    int *p = a;
    return (p != 0) ? 0 : 1;
}
'''.lstrip()

    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)

    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(out_path))
    assert res.success, "compile failed: " + "\n".join(res.errors)


def test_allow_equality_compare_void_ptrs(tmp_path):
    code = r'''
int main(){
    int a[1];
    void *p = (void*)a;
    void *q = (void*)a;
    return (p == q) ? 0 : 1;
}
'''.lstrip()

    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)

    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(out_path))
    assert res.success, "compile failed: " + "\n".join(res.errors)
