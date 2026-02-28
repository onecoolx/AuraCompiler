from pycc.compiler import Compiler


def test_reject_relational_compare_ptr_vs_int(tmp_path):
    code = r'''
int main(){
    int a[2];
    int *p = a;
    return (p < 1) ? 0 : 1;
}
'''.lstrip()

    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)

    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(out_path))
    assert not res.success
    msg = "\n".join(res.errors).lower()
    assert "pointer" in msg and "<" in msg


def test_reject_relational_compare_void_ptr(tmp_path):
    code = r'''
int main(){
    int a[2];
    void *p = (void*)a;
    void *q = (void*)(a + 1);
    return (p < q) ? 0 : 1;
}
'''.lstrip()

    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)

    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(out_path))
    assert not res.success
    msg = "\n".join(res.errors).lower()
    assert "void" in msg and "pointer" in msg
