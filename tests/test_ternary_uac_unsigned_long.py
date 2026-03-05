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


def test_ternary_uac_long_vs_unsigned_int(tmp_path):
    # C89 usual arithmetic conversions for ?: should compute a common type.
    # On LP64, long is 64-bit and can represent all values of unsigned int,
    # so the result type should be long (signed) in this case.
    code = r"""
int main(void) {
  unsigned int u = 1u;
  long a = -1L;
  long r = (u ? a : 0);
  return (r == -1L) ? 0 : 1;
}
"""
    assert _compile_and_run(tmp_path, code) == 0


def test_ternary_uac_long_vs_unsigned_long(tmp_path):
    # long vs unsigned long -> unsigned long.
    code = r"""
int main(void) {
  unsigned long u = 1ul;
  long a = -1L;
  unsigned long r = (u ? (unsigned long)a : 0ul);
  return (r == (unsigned long)-1L) ? 0 : 1;
}
"""
    assert _compile_and_run(tmp_path, code) == 0
