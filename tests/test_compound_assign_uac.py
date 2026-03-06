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


def test_compound_assign_u32_wraps(tmp_path: Path) -> None:
    # C89: for E1 op= E2, E1 is evaluated once; arithmetic is in the usual
    # arithmetic conversions domain, then converted back to type of E1.
    # For unsigned int, wrap modulo 2^32.
    code = r"""
int main(void){
  unsigned int x = 0u;
  x -= 1;
  return x == 0xffffffffu ? 0 : 1;
}
""".lstrip()
    assert _compile_and_run(tmp_path, code) == 0


def test_compound_assign_short_truncates(tmp_path: Path) -> None:
    # short promoted to int for arithmetic, then assigned back (truncation).
    # 32767 + 2 == 32769, truncated to 16-bit signed => -32767.
    code = r"""
int main(void){
  short s = 32767;
  s += 2;
  return s == (short)-32767 ? 0 : 1;
}
""".lstrip()
    assert _compile_and_run(tmp_path, code) == 0
