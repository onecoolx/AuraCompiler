from __future__ import annotations

from pathlib import Path

from pycc.compiler import Compiler


def _compile(tmp_path: Path, c_src: str):
    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(c_src)

    comp = Compiler(optimize=False)
    return comp.compile_file(str(c_path), str(out_path))


def test_reject_conflicting_function_param_count_same_tu(tmp_path: Path) -> None:
    # Same TU: conflicting prototypes should be rejected.
    code = r"""
int f(int a);
int f(int a, int b) { return a + b; }

int main(void){
  return f(1, 2);
}
""".lstrip()
    res = _compile(tmp_path, code)
    assert not res.success, "expected failure but succeeded"
