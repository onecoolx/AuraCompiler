from __future__ import annotations


import subprocess


from pycc.compiler import Compiler


def _compile_and_run(tmp_path, code: str) -> int:
  c_file = tmp_path / "test.c"
  out_path = tmp_path / "a.out"
  c_file.write_text(code)

  compiler = Compiler()
  res = compiler.compile_file(str(c_file), str(out_path))
  assert res.success, f"compile failed: {res.errors}\nASM:\n{res.assembly}"

  p = subprocess.run([str(out_path)], check=False)
  return p.returncode


def test_global_int_array_brace_initializer_zero_fill(tmp_path):
    src = r"""
int g[3] = {1, 2};
int main() {
  return g[0] == 1 && g[1] == 2 && g[2] == 0 ? 0 : 1;
}
"""
    assert _compile_and_run(tmp_path, src) == 0


def test_global_char_array_string_initializer_fixed_size(tmp_path):
    src = r"""
char s[4] = "hi";
int main() {
  /* expects: 'h','i','\0','\0' */
  return s[0] == 'h' && s[1] == 'i' && s[2] == 0 && s[3] == 0 ? 0 : 1;
}
"""
    assert _compile_and_run(tmp_path, src) == 0


def test_global_struct_brace_initializer_full(tmp_path):
    src = r"""
struct Point { int x; int y; };
struct Point p = {1, 2};
int main() {
  return p.x == 1 && p.y == 2 ? 0 : 1;
}
"""
    assert _compile_and_run(tmp_path, src) == 0


def test_global_struct_brace_initializer_partial_zero_fill(tmp_path):
    src = r"""
struct Point { int x; int y; };
struct Point p = {7};
int main() {
  return p.x == 7 && p.y == 0 ? 0 : 1;
}
"""
    assert _compile_and_run(tmp_path, src) == 0
