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


def test_local_char_array_string_initializer(tmp_path):
    code = r"""
int main(){
  char s[] = "hi";
    return (s[0] == 104 && s[1] == 105 && s[2] == 0) ? 0 : 1;
}
""".lstrip()
    assert _compile_and_run(tmp_path, code) == 0


def test_local_int_array_brace_initializer(tmp_path):
    code = r"""
int main(){
  int a[3] = {1, 2, 3};
  return (a[0] + a[1] + a[2]) == 6 ? 0 : 1;
}
""".lstrip()
    assert _compile_and_run(tmp_path, code) == 0


def test_local_int_array_zero_fill_brace_initializer(tmp_path):
    code = r"""
int main(){
  int a[3] = {1};
  return (a[0] == 1 && a[1] == 0 && a[2] == 0) ? 0 : 1;
}
""".lstrip()
    assert _compile_and_run(tmp_path, code) == 0
