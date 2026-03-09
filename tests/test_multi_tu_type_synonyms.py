from __future__ import annotations

from pathlib import Path

from pycc.compiler import Compiler


def test_signed_int_and_int_are_compatible_across_tus(tmp_path: Path):
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
signed int g;
""".lstrip(),
        encoding="utf-8",
    )

    comp = Compiler(optimize=False)
    res = comp.compile_files([str(a), str(b)], str(out))
    assert res.success, "unexpected failure: " + "\n".join(res.errors)
