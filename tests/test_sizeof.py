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


def test_sizeof_basic_types(tmp_path):
    code = """
int main(){
  return sizeof(int) + sizeof(char);
}
""".lstrip()
    assert _compile_and_run(tmp_path, code) == 5


def test_sizeof_pointer_type(tmp_path):
    code = """
int main(){
  return sizeof(int*) == 8;
}
""".lstrip()
    assert _compile_and_run(tmp_path, code) == 1


def test_sizeof_expr_form(tmp_path):
    code = """
int main(){
  int x = 0;
  return sizeof x;
}
""".lstrip()
    assert _compile_and_run(tmp_path, code) == 4
