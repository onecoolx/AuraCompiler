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


def test_sizeof_does_not_eval_postinc(tmp_path):
    # sizeof operand must not be evaluated.
    # Use compound assignment to ensure side effects would be observable.
    code = r'''
int main(void) {
  int i = 0;
  (void)sizeof(i += 1);
  return (i == 0) ? 0 : 1;
}
'''.lstrip()
    assert _compile_and_run(tmp_path, code) == 0


def test_sizeof_does_not_eval_assignment_expr(tmp_path):
    code = r'''
int main(void) {
  int i = 0;
  (void)sizeof(i = 123);
  return (i == 0) ? 0 : 1;
}
'''.lstrip()
    assert _compile_and_run(tmp_path, code) == 0
