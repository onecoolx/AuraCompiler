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


def test_struct_member_signed_char_right_shift_arithmetic(tmp_path):
    code = r"""
struct S { signed char sc; };

int main(void) {
  struct S s;
  s.sc = (signed char)-2; /* 0xFE */
  /* integral promotions: (int)s.sc == -2; right shift should be arithmetic */
  return ((s.sc >> 1) == -1) ? 0 : 1;
}
"""
    assert _compile_and_run(tmp_path, code) == 0


def test_struct_member_unsigned_char_right_shift_logical(tmp_path):
    code = r"""
struct S { unsigned char uc; };

int main(void) {
  struct S s;
  s.uc = (unsigned char)0xFE;
  /* integral promotions: (int)s.uc == 254; right shift should be logical on promoted int */
  return ((s.uc >> 1) == 127) ? 0 : 1;
}
"""
    assert _compile_and_run(tmp_path, code) == 0
