from __future__ import annotations

from pathlib import Path

from pycc.compiler import Compiler


def _compile_and_run(tmp_path: Path, c_src: str) -> int:
  c_path = tmp_path / "t.c"
  out_path = tmp_path / "t"
  c_path.write_text(c_src)

  comp = Compiler(optimize=False)
  res = comp.compile_file(str(c_path), str(out_path))
  assert res.success, "compile failed: " + "\n".join(res.errors)

  import subprocess

  p = subprocess.run([str(out_path)], check=False)
  return p.returncode


def test_integer_promotions_unsigned_char_add_int(tmp_path):
    # C integer promotions: unsigned char promotes to int (if int can represent all values),
    # then usual arithmetic conversions apply.
    code = r'''
int main(void){
  unsigned char uc = 250;
  int x = 10;
  int y = uc + x;
  return y == 260 ? 0 : 1;
}
'''
    assert _compile_and_run(tmp_path, code.lstrip()) == 0


def test_integer_promotions_unsigned_short_add_int(tmp_path):
    code = r'''
int main(void){
  unsigned short us = 60000;
  int x = 100;
  unsigned int y = us + x;
  return y == 60100U ? 0 : 1;
}
'''
    assert _compile_and_run(tmp_path, code.lstrip()) == 0


def test_uac_signed_unsigned_mixed_relational(tmp_path):
    # Ensure comparisons perform usual arithmetic conversions.
    # On typical ILP32/LP64, unsigned int vs int -> both convert to unsigned int.
    code = r'''
int main(void){
  int a = -1;
  unsigned int b = 1U;
  return (a < b) ? 1 : 0; /* (-1U < 1U) is false -> return 0 */
}
'''
    assert _compile_and_run(tmp_path, code.lstrip()) == 0


def test_uac_ternary_mixed_types(tmp_path):
    # Conditional operator uses usual arithmetic conversions for the second/third operands.
    code = r'''
int main(void){
  unsigned int u = 1U;
  int s = -1;
  unsigned int x = 0 ? u : s;
  return x == (unsigned int)-1 ? 0 : 1;
}
'''
    assert _compile_and_run(tmp_path, code.lstrip()) == 0
