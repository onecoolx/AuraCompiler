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


def test_signed_char_member_load_sign_ext(tmp_path):
    code = r'''
struct S { signed char a; };
static struct S s;
int main(void){
  s.a = (signed char)0xFF; /* -1 */
  return (int)s.a;         /* expect -1 */
}
'''
    # NOTE: process exit codes are modulo 256, so -1 shows up as 255.
    assert _compile_and_run(tmp_path, code) == 255


def test_unsigned_char_member_load_zero_ext(tmp_path):
    code = r'''
struct S { unsigned char a; };
static struct S s;
int main(void){
  s.a = (unsigned char)0xFF;
  return (int)s.a;         /* expect 255 */
}
'''
    assert _compile_and_run(tmp_path, code) == 255
