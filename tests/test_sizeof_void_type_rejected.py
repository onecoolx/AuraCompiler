from pycc.compiler import Compiler


def _compile(tmp_path, code: str):
    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)
    comp = Compiler(optimize=False)
    return comp.compile_file(str(c_path), str(out_path))


def test_sizeof_void_type_is_rejected(tmp_path):
    # C89 constraint: sizeof(void) is invalid (void is incomplete).
    code = r'''
int main(void) {
    return sizeof((void)0);
}
'''.lstrip()

    res = _compile(tmp_path, code)
    assert not res.success
    assert any("sizeof" in e.lower() and ("void" in e.lower() or "incomplete" in e.lower()) for e in res.errors)
