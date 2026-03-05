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


def test_plain_char_defaults_to_signed(tmp_path):
    # Document current backend behavior: plain `char` is treated as signed.
    # This is implementation-defined in C; we will likely make it configurable.
    code = r"""
int main(void) {
  char c = (char)-1;
  /* if signed: promotes to -1 */
  return ((int)c == -1) ? 0 : 1;
}
"""
    assert _compile_and_run(tmp_path, code) == 0
