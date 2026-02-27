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


def test_pointer_plus_int_scales_by_element_size(tmp_path):
    # For int*, p + 2 should advance by 2 * sizeof(int) (typically 8 bytes on our ABI assumptions).
    # We check runtime by indexing, not by inspecting generated asm.
    code = r'''
int main(){
    int a[4];
    a[0] = 10;
    a[2] = 77;
    int *p = a;
    return p[2] - 77;
}
'''.lstrip()

    assert _compile_and_run(tmp_path, code) == 0
