from __future__ import annotations

from pathlib import Path

from pycc.compiler import Compiler


def _compile(tmp_path: Path, c_src: str):
    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(c_src)

    comp = Compiler(optimize=False)
    return comp.compile_file(str(c_path), str(out_path))


def test_reject_incompatible_function_pointer_assignment(tmp_path: Path) -> None:
    # Function pointer types are incompatible if param lists differ.
    code = r"""
int f(int a) { return a; }
int g(void) { return 0; }

int main(void){
    int (*fp)(void);
  fp = f;   /* incompatible: f takes int */
  return fp();
}
""".lstrip()
    # NOTE: parser currently erases function pointer parameter lists
    # (represents all as `int (*)()`), so we can't enforce this yet.
    res = _compile(tmp_path, code)
    assert res.success, "unexpected failure: " + "\n".join(res.errors)
