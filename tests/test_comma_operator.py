import subprocess

import pytest

from pycc.compiler import Compiler


def _compile_and_run(tmp_path, code: str) -> int:
  c_path = tmp_path / "t.c"
  out_path = tmp_path / "t"
  c_path.write_text(code)

  comp = Compiler(optimize=False)
  res = comp.compile_file(str(c_path), str(out_path))
  assert res.success, "compile failed: " + "\n".join(res.errors)

  p = subprocess.run([str(out_path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
  return p.returncode


def test_comma_operator_evaluates_left_then_right(tmp_path):
    # (a = 1, a + 2) should evaluate to 3
    src = r"""
int main(){
  int a;
  a = 0;
  return (a = 1, a + 2) == 3 ? 0 : 1;
}
"""
    assert _compile_and_run(tmp_path, src.lstrip()) == 0


def test_comma_operator_lowest_precedence(tmp_path):
    # comma has lower precedence than ?:, so the expression should parse as:
    # ((1 ? 2 : 3), 4)
    src = r"""
int main(){
  int x;
  x = (1 ? 2 : 3, 4);
  return x == 4 ? 0 : 1;
}
"""
    assert _compile_and_run(tmp_path, src.lstrip()) == 0


def test_comma_operator_for_clause_allows_commas(tmp_path):
    # for(init; cond; inc) should allow comma-expressions in the inc clause.
    src = r"""
int main(){
  int i;
  int j;
  i = 0;
  j = 0;
  for(i = 0; i < 3; i = i + 1, j = j + 2) {
    ;
  }
  return (i == 3 && j == 6) ? 0 : 1;
}
"""
    assert _compile_and_run(tmp_path, src.lstrip()) == 0


def test_comma_operator_requires_expression_after_comma(tmp_path):
    src = r"""
int main(){
  int a;
  a = (1,);
  return 0;
}
"""
    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(src.lstrip())

    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(out_path))
    assert not res.success
