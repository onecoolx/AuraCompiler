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


def test_function_pointer_parameter_declarator(tmp_path: Path):
    # Complex declarator: parameter is a pointer to function taking int and returning int.
    code = r'''
    int apply(int (*f)(int), int x) {
      return f(x);
    }

    int inc(int a) { return a + 1; }

    int main(void) {
      return apply(inc, 41) == 42 ? 0 : 1;
    }
    '''.lstrip()

    assert _compile_and_run(tmp_path, code) == 0
