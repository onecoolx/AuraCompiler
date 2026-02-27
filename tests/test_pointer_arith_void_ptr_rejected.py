from pycc.compiler import Compiler


def test_void_pointer_arithmetic_is_rejected(tmp_path):
    code = r'''
int main(){
    void *p = (void*)0;
    p = p + 1;
    return 0;
}
'''.lstrip()

    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)

    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(out_path))
    assert not res.success
