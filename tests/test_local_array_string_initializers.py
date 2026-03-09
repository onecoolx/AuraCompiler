from __future__ import annotations

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


def test_local_char_array_string_initializer_infers_size_and_nul(tmp_path):
    # C89: char s[] = "hi"; has size 3 with trailing '\0'.
    code = r'''
int main(void){
  char s[] = "hi";
  return (sizeof(s) == 3 && s[0]=='h' && s[1]=='i' && s[2]==0) ? 0 : 1;
}
'''
    assert _compile_and_run(tmp_path, code) == 0


def test_local_int_array_brace_initializer_and_partial_zero(tmp_path):
    # C89: missing elements are zero-initialized.
    code = r'''
int main(void){
  int a[5] = {1,2};
  return (a[0]==1 && a[1]==2 && a[2]==0 && a[3]==0 && a[4]==0) ? 0 : 1;
}
'''
    assert _compile_and_run(tmp_path, code) == 0
