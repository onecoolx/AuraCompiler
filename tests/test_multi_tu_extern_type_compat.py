from __future__ import annotations

from pathlib import Path

from pycc.compiler import Compiler


def test_extern_decl_must_be_compatible_with_definition(tmp_path: Path):
    # C89: an extern declaration must have a type compatible with the
    # eventual external definition (across TUs).
    a = tmp_path / "a.c"
    b = tmp_path / "b.c"
    out = tmp_path / "a.out"

    a.write_text(
        """
extern int g;
int main(void){ return 0; }
""".lstrip(),
        encoding="utf-8",
    )
    b.write_text(
        """
long g;
""".lstrip(),
        encoding="utf-8",
    )

    comp = Compiler(optimize=False)
    res = comp.compile_files([str(a), str(b)], str(out))
    assert not res.success
    msg = "\n".join(res.errors).lower()
    assert "incompatible" in msg and "g" in msg
