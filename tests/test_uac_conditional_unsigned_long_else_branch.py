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


def test_uac_conditional_operator_unsigned_long_else_branch(tmp_path):
    # Else branch picks -1, but the result type should still be unsigned long.
    code = r"""
int main(void) {
  unsigned long x = 1UL;
  unsigned long y = (0 ? x : -1);
  return (y == (unsigned long)-1) ? 0 : 1;
}
""".lstrip()
    assert _compile_and_run(tmp_path, code) == 0
