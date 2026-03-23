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


def test_array_partial_init_zero_fills(tmp_path: Path) -> None:
    # Unspecified elements should be zero-initialized.
    code = r"""
int main(void){
  int a[4] = {1, 2};
  if (a[0] != 1) return 1;
  if (a[1] != 2) return 2;
  if (a[2] != 0) return 3;
  if (a[3] != 0) return 4;
  return 0;
}
""".lstrip()
    assert _compile_and_run(tmp_path, code) == 0


def test_nested_brace_elision_2d_array(tmp_path: Path) -> None:
    # Brace elision for nested aggregates.
    code = r"""
int main(void){
  int a[2][2] = { 1, 2, 3, 4 };
  if (a[0][0] != 1) return 1;
  if (a[0][1] != 2) return 2;
  if (a[1][0] != 3) return 3;
  if (a[1][1] != 4) return 4;
  return 0;
}
""".lstrip()
    assert _compile_and_run(tmp_path, code) == 0


def test_struct_partial_init_zero_fills(tmp_path: Path) -> None:
    code = r"""
struct S { int a; int b; };
int main(void){
  struct S s = { 7 };
  return (s.a == 7 && s.b == 0) ? 0 : 1;
}
""".lstrip()
    assert _compile_and_run(tmp_path, code) == 0
