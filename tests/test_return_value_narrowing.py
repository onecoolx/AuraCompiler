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


def test_return_unsigned_char_truncates(tmp_path: Path) -> None:
    # Returning unsigned char should truncate modulo 256.
    code = r"""
unsigned char f(void){
  return (unsigned char)256;
}
int main(void){
  return f() == (unsigned char)0 ? 0 : 1;
}
""".lstrip()
    assert _compile_and_run(tmp_path, code) == 0


def test_return_short_sign_extends(tmp_path: Path) -> None:
    # Returning short should preserve sign when used as int in the caller.
    code = r"""
short f(void){
  return (short)-1;
}
int main(void){
  int x = f();
  return x == -1 ? 0 : 1;
}
""".lstrip()
    assert _compile_and_run(tmp_path, code) == 0
