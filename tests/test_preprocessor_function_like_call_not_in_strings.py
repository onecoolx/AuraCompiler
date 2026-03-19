import textwrap

from pycc.preprocessor import Preprocessor


def _pp_text(tmp_path, source_text):
    src = tmp_path / "main.c"
    src.write_text(textwrap.dedent(source_text).lstrip(), encoding="utf-8")
    pp = Preprocessor(include_paths=[str(tmp_path)])
    return pp.preprocess(str(src)).text


def test_function_like_macro_not_expanded_inside_string_literal(tmp_path):
    out = _pp_text(
        tmp_path,
        r"""
        #define F(x) x

        const char *s = "F(1)";
        int y = F(2);
        """,
    )

    assert 'const char *s = "F(1)";' in out
    assert "int y = 2;" in out
