from pathlib import Path

from pycc.compiler import Compiler


def test_unified_error_format_parser(tmp_path: Path):
    src = tmp_path / "t.c"
    # Intentionally broken syntax.
    src.write_text("int main( { return 0; }\n", encoding="utf-8")

    comp = Compiler(optimize=False)
    res = comp.compile_file(str(src), str(tmp_path / "out.s"))
    assert not res.success
    msg = "\n".join(res.errors)

    # GCC-compatible format: <file>:<line>:<col>: error: syntax: <message>
    assert "error: syntax:" in msg, msg
    assert "t.c:" in msg, msg


def test_unified_error_format_semantics(tmp_path: Path):
    src = tmp_path / "t.c"
    src.write_text(
        """
        int main(void) {
          register int x;
          int *p = &x;
          return 0;
        }
        """.lstrip(),
        encoding="utf-8",
    )

    comp = Compiler(optimize=False)
    res = comp.compile_file(str(src), str(tmp_path / "out.s"))
    assert not res.success
    msg = "\n".join(res.errors)

    # GCC-compatible format: <file>:<line>:<col>: error: semantics: <message>
    assert "error: semantics:" in msg, msg
    assert "t.c:" in msg, msg
