from __future__ import annotations

from pathlib import Path

from pycc.compiler import Compiler


def test_multiple_strong_definitions_rejected_pre_link(tmp_path: Path):
    a = tmp_path / "a.c"
    b = tmp_path / "b.c"
    out = tmp_path / "a.out"

    a.write_text(
        """
int g = 1;
int main(void){ return g; }
""".lstrip(),
        encoding="utf-8",
    )
    b.write_text(
        """
int g = 2;
""".lstrip(),
        encoding="utf-8",
    )

    comp = Compiler(optimize=False)
    res = comp.compile_files([str(a), str(b)], str(out))
    assert not res.success
    msg = "\n".join(res.errors).lower()
    assert "multiple" in msg and "definition" in msg and "g" in msg
