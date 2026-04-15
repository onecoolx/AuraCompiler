from pycc.compiler import Compiler


def _compile_and_run(tmp_path, code: str) -> int:
    import subprocess

    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)

    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(out_path))
    assert res.success, "compile failed: " + "\n".join(res.errors)

    p = subprocess.run([str(out_path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return int(p.returncode)


def test_sizeof_array_parameter_is_pointer_size(tmp_path):
    # C89 §6.7.1: `int a[]` in a parameter list adjusts to `int *a`,
    # so sizeof(a) should be pointer size (8 on x86-64).
    code = r"""
int f(int a[]) {
    return (sizeof(a) == 8) ? 0 : 1;
}

int main(void) {
    int x[3];
    return f(x);
}
""".lstrip()
    assert _compile_and_run(tmp_path, code) == 0
