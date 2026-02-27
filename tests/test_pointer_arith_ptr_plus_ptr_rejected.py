from pycc.compiler import Compiler


def test_pointer_plus_pointer_is_rejected(tmp_path):
    code = r'''
int main(){
    int a[2];
    int *p = a;
    int *q = a;
    return (int)(p + q);
}
'''.lstrip()

    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)

    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(out_path))
    assert not res.success
