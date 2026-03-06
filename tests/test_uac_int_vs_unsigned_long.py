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


def test_uac_int_with_unsigned_long_addition(tmp_path: Path) -> None:
    # C89 usual arithmetic conversions: int + unsigned long => unsigned long.
    # With x = -1, y = 1UL, x converts to ULONG_MAX and wraps: ULONG_MAX + 1 == 0.
    code = r"""
int main(void){
  int x = -1;
  unsigned long y = 1UL;
  unsigned long z = x + y;
  return z == 0UL ? 0 : 1;
}
""".lstrip()
    assert _compile_and_run(tmp_path, code) == 0


def test_uac_relational_int_with_unsigned_long(tmp_path: Path) -> None:
    # Mixed signed/unsigned: (-1 < 1UL) is false because -1 converts to ULONG_MAX.
    code = r"""
int main(void){
  int x = -1;
  unsigned long y = 1UL;
  return (x < y) ? 1 : 0;
}
""".lstrip()
    assert _compile_and_run(tmp_path, code) == 0
