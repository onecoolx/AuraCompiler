from __future__ import annotations

from pathlib import Path

from pycc.compiler import Compiler


def _compile_and_run(tmp_path: Path, code: str) -> int:
    import subprocess

    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)

    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(out_path))
    assert res.success, "compile failed: " + "\n".join(res.errors)

    p = subprocess.run([str(out_path)], check=False)
    return p.returncode


def test_array_of_function_pointers_declarator(tmp_path: Path):
    # Complex declarator: array of function pointers.
    # int (*fp[2])(int);
    code = r'''
    int inc(int a) { return a + 1; }
    int dec(int a) { return a - 1; }

    int main(void) {
      int (*fp[2])(int);
      fp[0] = inc;
      fp[1] = dec;
      return (fp[0](41) == 42 && fp[1](43) == 42) ? 0 : 1;
    }
    '''.lstrip()

    assert _compile_and_run(tmp_path, code) == 0
