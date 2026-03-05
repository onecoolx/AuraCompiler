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


def test_struct_padding_char_int_char(tmp_path):
    src = r"""
struct S { char a; int b; char c; };
static struct S s;
int main(void) {
  char *p = (char*)&s;
  p[0] = 0x11;
  p[1] = 0x22;
  p[2] = 0x33;
  p[3] = 0x44;
  p[4] = 0x55;
  p[5] = 0x66;
  p[6] = 0x77;
  p[7] = 0x88;
  p[8] = 0x99;
  p[9] = 0xaa;
  p[10] = 0xbb;
  p[11] = 0xcc;

    /*
        Validate layout via member access (no raw loads).
        This exercises:
            - store_member lowering for globals
            - load_member lowering for globals
            - struct padding between `char` and `int`
    */
    s.a = (char)0x11;
    s.b = (int)0x88776655u;
    s.c = (char)0x99;

    /* Expect: a at 0, b at 4, c at 8 (LP64 SysV) */
    if ((unsigned char)s.a != 0x11) return 1;
    if ((unsigned int)s.b != 0x88776655u) return 2;
    if ((unsigned char)s.c != 0x99) return 3;
  return 0;
}
"""
    assert _compile_and_run(tmp_path, src) == 0
