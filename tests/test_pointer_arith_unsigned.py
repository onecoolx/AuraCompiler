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


def test_unsigned_char_pointer_difference_in_elements(tmp_path):
    code = r'''
int main(){
    unsigned char a[5];
    unsigned char *p1 = a;
    unsigned char *p2 = a + 3;
    return (int)(p2 - p1);
}
'''.lstrip()
    assert _compile_and_run(tmp_path, code) == 3


def test_unsigned_short_pointer_difference_in_elements(tmp_path):
    code = r'''
int main(){
    unsigned short a[5];
    unsigned short *p1 = a;
    unsigned short *p2 = a + 3;
    return (int)(p2 - p1);
}
'''.lstrip()
    assert _compile_and_run(tmp_path, code) == 3
