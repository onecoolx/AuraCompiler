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


def test_promotion_short_to_int_sign_preserved(tmp_path: Path) -> None:
    # short promotes to int with sign-extension.
    code = r"""
int main(void){
  short s = (short)-1;
  int x = s;
  return x == -1 ? 0 : 1;
}
""".lstrip()
    assert _compile_and_run(tmp_path, code) == 0


def test_promotion_unsigned_short_to_int_zero_extended(tmp_path: Path) -> None:
    # On our target model, unsigned short promotes to int (not unsigned int),
    # but its value must be preserved (zero-extension).
    code = r"""
int main(void){
  unsigned short us = (unsigned short)65535;
  int x = us;
  return x == 65535 ? 0 : 1;
}
""".lstrip()
    assert _compile_and_run(tmp_path, code) == 0
