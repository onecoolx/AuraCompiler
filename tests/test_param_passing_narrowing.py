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


def test_param_unsigned_char_truncates(tmp_path: Path) -> None:
    # Passing int to unsigned char parameter should convert modulo 256.
    code = r"""
int f(unsigned char x){
  return x == (unsigned char)0 ? 0 : 1;
}
int main(void){
  return f(256);
}
""".lstrip()
    assert _compile_and_run(tmp_path, code) == 0


def test_param_short_sign_extends(tmp_path: Path) -> None:
    # Passing short parameter and using it as int inside callee should preserve sign.
    code = r"""
int f(short s){
  int x = s;
  return x == -1 ? 0 : 1;
}
int main(void){
  return f((short)-1);
}
""".lstrip()
    assert _compile_and_run(tmp_path, code) == 0
