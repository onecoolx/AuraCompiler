from __future__ import annotations

from pathlib import Path

from pycc.compiler import Compiler


def _compile(tmp_path: Path, c_src: str):
    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(c_src)
    comp = Compiler(optimize=False)
    return comp.compile_file(str(c_path), str(out_path))


def test_global_int_array_excess_elements_is_error(tmp_path: Path) -> None:
    code = r"""
int g[2] = {1,2,3};
int main(void){ return g[0]; }
""".lstrip()
    res = _compile(tmp_path, code)
    assert not res.success


def test_global_2d_int_array_excess_elements_is_error(tmp_path: Path) -> None:
    code = r"""
int g[2][2] = { {1,2}, {3,4}, {5,6} };
int main(void){ return g[0][0]; }
""".lstrip()
    res = _compile(tmp_path, code)
    assert not res.success
