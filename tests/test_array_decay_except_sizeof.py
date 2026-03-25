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


def test_sizeof_array_not_pointer(tmp_path: Path) -> None:
    # In expressions, arrays usually decay to pointers, but sizeof(array)
    # uses the array type and yields total array size.
    code = r"""
int main(void){
  int a[3];
  return sizeof(a) == 3 * (int)sizeof(int) ? 0 : 1;
}
""".lstrip()
    assert _compile_and_run(tmp_path, code) == 0
