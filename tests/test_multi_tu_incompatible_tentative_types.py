from __future__ import annotations

from pathlib import Path

from pycc.compiler import Compiler


def test_incompatible_tentative_definitions_across_tus_is_rejected(tmp_path: Path):
    # C89: multiple tentative definitions for the same external object across
    # translation units must have compatible types.
    #
    # Today we enforce this in the driver multi-file pipeline (pre-link) so the
    # error is deterministic and doesn't depend on the system linker's behavior.
    a = tmp_path / "a.c"
    b = tmp_path / "b.c"
    out = tmp_path / "a.out"

    a.write_text(
        """
int g;
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
    msg = "\n".join(res.errors)
    assert "incompatible" in msg.lower() and "g" in msg
