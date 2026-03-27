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


def test_array_decay_in_expression(tmp_path: Path) -> None:
    # Array name in expression decays to pointer to first element.
    code = r"""
int main(void){
  int a[3] = {1,2,3};
  int *p = a;  // decay
  return *p == 1 ? 0 : 1;
}
""".lstrip()
    assert _compile_and_run(tmp_path, code) == 0


def test_array_decay_in_function_call(tmp_path: Path) -> None:
    # Array decays in function call arguments.
    code = r"""
void f(int *p) {
  *p = 42;
}

int main(void){
  int a[1] = {0};
  f(a);  // decay
  return a[0] == 42 ? 0 : 1;
}
""".lstrip()
    assert _compile_and_run(tmp_path, code) == 0


def test_function_decay_in_assignment(tmp_path: Path) -> None:
    # Function name decays to function pointer in assignment.
    code = r"""
int f(void) { return 42; }

int main(void){
  int (*fp)(void) = f;  // decay
  return fp() == 42 ? 0 : 1;
}
""".lstrip()
    assert _compile_and_run(tmp_path, code) == 0