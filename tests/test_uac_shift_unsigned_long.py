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


def test_uac_shift_left_unsigned_long(tmp_path):
    code = r"""
int main(void) {
  unsigned long x = 1UL;
  unsigned long y = x << 63;
  return (y != 0UL) ? 0 : 1;
}
""".lstrip()
    assert _compile_and_run(tmp_path, code) == 0
