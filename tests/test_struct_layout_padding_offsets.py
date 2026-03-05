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


def test_struct_member_offsets_char_int_char(tmp_path):
    src = r"""
struct S { char a; int b; char c; };
int main(void) {
  struct S s;
  char *base = (char*)&s;
  int off_b = (int)((char*)&s.b - base);
  int off_c = (int)((char*)&s.c - base);
  /* Expect: b at 4, c at 8 */
  if (off_b != 4) return 1;
  if (off_c != 8) return 2;
  return 0;
}
"""
    assert _compile_and_run(tmp_path, src) == 0
