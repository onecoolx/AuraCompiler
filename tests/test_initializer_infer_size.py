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
    return p.returncode


def test_local_int_array_infer_size_from_brace_initializer(tmp_path):
    code = r"""
int main(){
  int a[] = {1, 2, 3, 4};
  return (a[0] + a[1] + a[2] + a[3]) == 10 ? 0 : 1;
}
""".lstrip()
    assert _compile_and_run(tmp_path, code) == 0
