import textwrap

from pycc.preprocessor import Preprocessor


def _pp_text(tmp_path, source_text):
    src = tmp_path / "main.c"
    src.write_text(textwrap.dedent(source_text).lstrip(), encoding="utf-8")
    pp = Preprocessor(include_paths=[str(tmp_path)])
    return pp.preprocess(str(src)).text


def test_function_like_macro_not_expanded_inside_char_literal(tmp_path):
    out = _pp_text(
        tmp_path,
        r"""
        #define F(x) x

        int c = 'F';
        int y = F(2);
        """,
    )

    assert "int c = 'F';" in out
    assert "int y = 2;" in out
