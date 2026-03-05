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


def test_addr_of_member_points_into_object(tmp_path):
    code = r'''
struct S { int x; int y; };
int main(void){
  struct S s;
  int *px = &s.x;
  int *py = &s.y;
  /* Expect offsets: 0 and 4 */
  if ((char*)py - (char*)px != 4) return 1;
  *px = 11;
  *py = 22;
  return (s.x == 11 && s.y == 22) ? 0 : 2;
}
'''
    assert _compile_and_run(tmp_path, code) == 0


def test_addr_of_member_for_global_struct(tmp_path):
    code = r'''
struct S { int x; int y; };
static struct S s;
int main(void){
  int *py = &s.y;
  *py = 7;
  return s.y == 7 ? 0 : 1;
}
'''
    assert _compile_and_run(tmp_path, code) == 0
