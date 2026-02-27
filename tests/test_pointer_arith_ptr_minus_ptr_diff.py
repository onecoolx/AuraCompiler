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


def test_pointer_minus_pointer_yields_element_distance(tmp_path):
    # C89: p2 - p1 yields ptrdiff_t number of elements.
    # Our subset returns int in registers; verify runtime value.
    code = r'''
int main(){
    int a[8];
    int *p1 = a + 1;
    int *p2 = a + 6;
    return (int)(p2 - p1) - 5;
}
'''.lstrip()

    assert _compile_and_run(tmp_path, code) == 0
