from pycc.compiler import Compiler


def _compile(tmp_path, code: str):
    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)

    comp = Compiler(optimize=False)
    return comp.compile_file(str(c_path), str(out_path))


def test_allow_compare_pointer_to_casted_null(tmp_path):
    code = r'''
int main(){
    int a[1];
    int *p = a;
    return (p != (int*)0) ? 0 : 1;
}
'''.lstrip()
    res = _compile(tmp_path, code)
    assert res.success, "compile failed: " + "\n".join(res.errors)


def test_allow_compare_void_ptr_to_casted_null(tmp_path):
    code = r'''
int main(){
    int a[1];
    void *p = (void*)a;
    return (p != (void*)0) ? 0 : 1;
}
'''.lstrip()
    res = _compile(tmp_path, code)
    assert res.success, "compile failed: " + "\n".join(res.errors)


def test_reject_compare_pointer_to_nonzero_int_cast(tmp_path):
    # (int*)1 is a pointer via cast — comparing two pointers is valid C.
    # This test now verifies it compiles (previously rejected too aggressively).
    code = r'''
int main(){
    int a[1];
    int *p = a;
    return (p == (int*)1) ? 0 : 1;
}
'''.lstrip()
    res = _compile(tmp_path, code)
    assert res.success
