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


def test_int_pointer_add_scaling(tmp_path):
    # Verify that p+1 advances by sizeof(int) bytes.
    code = r'''
int main(){
  int a[3];
  int *p;
  a[0] = 7;
  a[1] = 42;
  a[2] = 9;
  p = a;
    return p[1];
}
'''.lstrip()
    assert _compile_and_run(tmp_path, code) == 42


def test_char_pointer_add_scaling(tmp_path):
        # Verify that char* indexing uses byte addressing.
        code = r'''
int main(){
    char a[3];
    char *p;
    a[0] = 7;
    a[1] = 42;
    a[2] = 9;
    p = a;
    return p[1];
}
'''.lstrip()
        assert _compile_and_run(tmp_path, code) == 42


def test_pointer_difference_in_elements(tmp_path):
        # (p2 - p1) should be the element distance (subset: int* only).
        code = r'''
int main(){
    int a[5];
    int *p1 = a;
    int *p2 = a + 3;
    return (int)(p2 - p1);
}
'''.lstrip()
        assert _compile_and_run(tmp_path, code) == 3


def test_char_pointer_difference_in_elements(tmp_path):
    # (p2 - p1) should be the element distance for char*.
    code = r'''
int main(){
    char a[5];
    char *p1 = a;
    char *p2 = a + 3;
    return (int)(p2 - p1);
}
'''.lstrip()
    assert _compile_and_run(tmp_path, code) == 3
