def test_global_char_ptr_string_initializer(tmp_path):
    from pycc.compiler import Compiler
    import subprocess

    # C89: pointers may be initialized with address constants.
    # "hi" has type char[3] and decays to char* in initializer.
    src = tmp_path / "gsp.c"
    src.write_text(
        r'''
char *p = "hi";
int main(){
    return p[0] + p[1];
}
'''.lstrip()
    )

    out = tmp_path / "gsp"
    comp = Compiler(optimize=False)
    res = comp.compile_file(str(src), str(out))
    assert res.success, "compile failed: " + "\n".join(res.errors)

    r = subprocess.run([str(out)], capture_output=True, text=True)
    # POSIX exit status is 8-bit; 104+105=209 fits.
    assert r.returncode == (ord('h') + ord('i'))
