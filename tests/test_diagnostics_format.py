from pathlib import Path

from pycc.compiler import Compiler


def test_diagnostic_format_includes_location_for_parser_error(tmp_path: Path):
    # Missing identifier after 'int' should be a parser error with a location.
    src = tmp_path / "t.c"
    src.write_text("int main( { return 0; }\n", encoding="utf-8")

    comp = Compiler(optimize=False)
    # Only need to run through syntax; avoid toolchain/linker noise.
    res = comp.compile_file(str(src), str(tmp_path / "out.s"))
    assert not res.success
    msg = "\n".join(res.errors)
    # GCC-compatible format: <file>:<line>:<col>: error: syntax: <message>
    assert "error: syntax:" in msg
    assert "t.c:" in msg


def test_diagnostic_format_includes_location_for_semantic_error(tmp_path: Path):
    # Taking address of register variable should be a semantic error with location.
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
    assert "error: semantics:" in msg
    assert "t.c:" in msg
