from pycc.compiler import Compiler


def _compile(tmp_path, code: str):
    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)

    comp = Compiler(optimize=False)
    return comp.compile_file(str(c_path), str(out_path))


def test_cast_pointer_to_int_rejected(tmp_path):
    # C89: casts between pointers and integers are permitted (implementation-defined).
    # This compiler subset currently allows them.
    code = r"""
int main(void) {
    int x = 0;
    void *p = &x;
    return (int)p;
}
""".lstrip()
    res = _compile(tmp_path, code)
    assert res.success


def test_cast_int_to_pointer_rejected(tmp_path):
    # C89: casts between integers and pointers are permitted (implementation-defined).
    # This compiler subset currently allows them.
    code = r"""
int main(void) {
    int x = 0;
    void *p = (void *)x;
    return p == 0;
}
""".lstrip()
    res = _compile(tmp_path, code)
    assert res.success
