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


def test_unsigned_char_load_zero_ext(tmp_path):
    # Ensure loads from unsigned char* are zero-extended.
    # NOTE: keep locals initialized to avoid relying on uninitialized stack.
    code = r'''
int main(){
    unsigned char x = 0;
    unsigned char *p = &x;
    *p = 0xff;
    return (*p == 255) ? 0 : 1;
}
'''.lstrip()
    assert _compile_and_run(tmp_path, code) == 0


def test_signed_char_load_sign_ext(tmp_path):
    # Ensure loads from signed char* are sign-extended.
    code = r'''
int main(){
    signed char x = 0;
    signed char *p = &x;
    *p = (signed char)0xff;
    return (*p == -1) ? 0 : 1;
}
'''.lstrip()
    assert _compile_and_run(tmp_path, code) == 0


def test_unsigned_short_load_zero_ext(tmp_path):
    code = r'''
int main(){
    unsigned short x = 0;
    unsigned short *p = &x;
    *p = 0xffff;
    return (*p == 65535) ? 0 : 1;
}
'''.lstrip()
    assert _compile_and_run(tmp_path, code) == 0


def test_short_load_sign_ext(tmp_path):
    code = r'''
int main(){
    short x = 0;
    short *p = &x;
    *p = (short)0xffff;
    return (*p == -1) ? 0 : 1;
}
'''.lstrip()
    assert _compile_and_run(tmp_path, code) == 0
