import textwrap

from pycc.preprocessor import Preprocessor


def _pp_text(tmp_path, source_text, *, include_paths=()):
    src = tmp_path / "main.c"
    src.write_text(textwrap.dedent(source_text).lstrip(), encoding="utf-8")
    pp = Preprocessor(include_paths=[str(p) for p in include_paths])
    return pp.preprocess(str(src)).text


def test_include_quotes_allows_line_splice_in_header_name(tmp_path):
    # header name becomes: a.h
    (tmp_path / "a.h").write_text("int ok;\n", encoding="utf-8")

    out = _pp_text(
        tmp_path,
        """
        #include "a\\
        .h"
        """,
    )

    assert "int ok;" in out


def test_include_angle_allows_line_splice_in_header_name(tmp_path):
    inc = tmp_path / "inc"
    inc.mkdir()
    # header name becomes: xy.h (newline removed; whitespace may appear but should be removed in header-name)
    (inc / "xy.h").write_text("int ok2;\n", encoding="utf-8")

    out = _pp_text(
        tmp_path,
        """
        #include <x\\
        y.h>
        """,
        include_paths=(inc,),
    )

    assert "int ok2;" in out
