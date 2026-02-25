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


def test_sizeof_short_long_unsigned(tmp_path):
    code = """
int main(){
  if (sizeof(short) != 2) return 1;
  if (sizeof(long) != 8) return 2;
  if (sizeof(unsigned) != 4) return 3;
  if (sizeof(unsigned long) != 8) return 4;
  return 0;
}
""".lstrip()
    assert _compile_and_run(tmp_path, code) == 0


def test_short_truncation(tmp_path):
    code = """
int main(){
  short x;
  x = 0x12345;
  /* 0x12345 truncated to 16 bits = 0x2345 */
  return x == 0x2345 ? 0 : 1;
}
""".lstrip()
    assert _compile_and_run(tmp_path, code) == 0


def test_unsigned_int_compare(tmp_path):
    code = """
int main(){
  unsigned int u;
  u = 0xffffffff;
  /* if loaded with sign-extension, this becomes -1 and fails the compare */
  return (u > 0) ? 0 : 1;
}
""".lstrip()
    assert _compile_and_run(tmp_path, code) == 0


def test_unsigned_int_vs_signed_zero_compare(tmp_path):
        code = r'''
int main(){
    unsigned int u;
    u = 0xffffffff; /* 4294967295 */
    /* must be true as unsigned compare */
    return (u > (int)0) ? 0 : 1;
}
'''.lstrip()
        assert _compile_and_run(tmp_path, code) == 0


def test_unsigned_long_compare(tmp_path):
        code = r'''
int main(){
    unsigned long u;
    u = 0xffffffffffffffff;
    /* unsigned long max must be > 0 */
    return (u > 0) ? 0 : 1;
}
'''.lstrip()
        assert _compile_and_run(tmp_path, code) == 0
