import textwrap

from pycc.preprocessor import Preprocessor


def _pp_text(tmp_path, source_text):
    src = tmp_path / "main.c"
    src.write_text(textwrap.dedent(source_text).lstrip(), encoding="utf-8")
    pp = Preprocessor(include_paths=[str(tmp_path)])
    return pp.preprocess(str(src)).text


def test_function_like_macro_does_not_match_inside_longer_identifier(tmp_path):
    out = _pp_text(
        tmp_path,
        """
        #define F(x) x

        int a = FF(1);
        int b = F(2);
        """,
    )

    # Only the real call should expand.
    assert "int a = FF(1);" in out
    assert "int b = 2;" in out
