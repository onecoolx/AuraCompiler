from pycc.compiler import Compiler


def _compile_and_run(tmp_path, code: str) -> int:
    import subprocess

    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code, encoding="utf-8")

    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(out_path))
    assert res.success, "compile failed: " + "\n".join(res.errors)

    p = subprocess.run([str(out_path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return p.returncode


def test_sizeof_local_array_is_total_bytes(tmp_path):
    code = r"""
int main(){
    int a[3];
    return (sizeof(a) == 12) ? 0 : 1;
}
""".lstrip()
    assert _compile_and_run(tmp_path, code) == 0


def test_sizeof_array_element_is_element_size(tmp_path):
    code = r"""
int main(){
    int a[3];
    return (sizeof(a[0]) == 4) ? 0 : 1;
}
""".lstrip()
    assert _compile_and_run(tmp_path, code) == 0


def test_sizeof_pointer_to_first_element_is_pointer_size(tmp_path):
    code = r"""
int main(){
    int a[3];
    int* p = &a[0];
    return (sizeof(p) == 8) ? 0 : 1;
}
""".lstrip()
    assert _compile_and_run(tmp_path, code) == 0
