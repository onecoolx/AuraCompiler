import textwrap

from pycc.preprocessor import Preprocessor


def _pp_text(tmp_path, source_text, *, include_paths=()):
    src = tmp_path / "main.c"
    src.write_text(textwrap.dedent(source_text).lstrip(), encoding="utf-8")
    pp = Preprocessor(include_paths=[str(p) for p in include_paths])
    return pp.preprocess(str(src)).text


def test_include_quotes_allows_comments_before_header_name(tmp_path):
    (tmp_path / "x.h").write_text("int ok;\n", encoding="utf-8")

    out = _pp_text(
        tmp_path,
        r"""
        #include /*comment*/ "x.h"
        """,
    )

    assert "int ok;" in out


def test_include_angle_allows_comments_inside_header_name(tmp_path):
    inc = tmp_path / "inc"
    inc.mkdir()
    (inc / "xy.h").write_text("int ok2;\n", encoding="utf-8")

    out = _pp_text(
        tmp_path,
        r"""
        #include <x/*comment*/y.h>
        """,
        include_paths=(inc,),
    )

    assert "int ok2;" in out
