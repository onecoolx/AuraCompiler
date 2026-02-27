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


def test_store_through_int_pointer(tmp_path):
    code = r'''
int main(){
    int x;
    int *p = &x;
    *p = 123;
    return x - 123;
}
'''.lstrip()
    assert _compile_and_run(tmp_path, code) == 0


def test_store_through_char_pointer(tmp_path):
    code = r'''
int main(){
    int x;
    char *p = (char*)&x;
    *p = 0x7f;
    return ((unsigned char*)p)[0] == 0x7f ? 0 : 1;
}
'''.lstrip()
    assert _compile_and_run(tmp_path, code) == 0
