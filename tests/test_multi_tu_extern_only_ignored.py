from __future__ import annotations

from pathlib import Path

from pycc.compiler import Compiler


def test_pure_extern_declarations_are_ignored_by_multi_tu_validator(tmp_path: Path):
    # Multi-TU validator should not attempt to enforce/resolve extern-only
    # declarations if no TU in the compilation set provides a declaration/definition.
    # (This commonly happens with headers.)
    a = tmp_path / "a.c"
    out = tmp_path / "a.out"

    a.write_text(
        """
extern int g;
int main(void){ return 0; }
""".lstrip(),
        encoding="utf-8",
    )

    comp = Compiler(optimize=False)
    res = comp.compile_files([str(a)], str(out))
    assert res.success, "unexpected failure: " + "\n".join(res.errors)
