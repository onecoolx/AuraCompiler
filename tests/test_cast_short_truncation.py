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


def test_cast_signed_short_sign_extends(tmp_path: Path) -> None:
    # (signed short)0x8001 should be negative after cast (-32767).
    code = r"""
int main(void){
  int x = 0x8001;
  int y = (signed short)x;
  return y < 0 ? 0 : 1;
}
""".lstrip()
    assert _compile_and_run(tmp_path, code) == 0


def test_cast_unsigned_short_truncates(tmp_path: Path) -> None:
    # (unsigned short)0x10000 == 0.
    code = r"""
int main(void){
  unsigned int x = 0x10000u;
  unsigned int y = (unsigned short)x;
  return y == 0u ? 0 : 1;
}
""".lstrip()
    assert _compile_and_run(tmp_path, code) == 0
