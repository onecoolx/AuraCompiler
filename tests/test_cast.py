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


def test_cast_to_char(tmp_path):
    code = """
int main(){
  return (char)65;
}
""".lstrip()
    assert _compile_and_run(tmp_path, code) == 65


def test_cast_parenthesized_expr_vs_cast(tmp_path):
    # Ensure (expression) still parses as expression, not a cast.
    code = """
int main(){
  return (40 + 2);
}
""".lstrip()
    assert _compile_and_run(tmp_path, code) == 42


def test_cast_to_pointer_and_compare_zero(tmp_path):
    code = """
int main(){
  int *p;
  p = (int*)0;
  return p == 0;
}
""".lstrip()
    assert _compile_and_run(tmp_path, code) == 1
