from __future__ import annotations

from pathlib import Path

from pycc.compiler import Compiler


def _compile(tmp_path: Path, c_src: str):
    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(c_src)
    comp = Compiler(optimize=False)
    return comp.compile_file(str(c_path), str(out_path))


def test_global_struct_initializer_excess_elements_is_error(tmp_path: Path) -> None:
    code = r"""
struct S { int a; };
struct S g = { 1, 2 };

int main(void){ return g.a; }
""".lstrip()
    res = _compile(tmp_path, code)
    assert not res.success


def test_global_union_initializer_excess_elements_is_error(tmp_path: Path) -> None:
    code = r"""
union U { int a; int b; };
union U g = { 1, 2 };

int main(void){ return g.a; }
""".lstrip()
    res = _compile(tmp_path, code)
    assert not res.success
