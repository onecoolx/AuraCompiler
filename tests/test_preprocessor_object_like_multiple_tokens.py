import textwrap

from pycc.preprocessor import Preprocessor


def _pp_text(tmp_path, source_text: str) -> str:
    src = tmp_path / "main.c"
    src.write_text(textwrap.dedent(source_text).lstrip(), encoding="utf-8")
    pp = Preprocessor(include_paths=[str(tmp_path)])
    return pp.preprocess(str(src)).text


def test_object_like_macro_expands_to_multiple_tokens(tmp_path):
    out = _pp_text(
        tmp_path,
        """
        #define A 1 + 2
        int x = A;
        """,
    )

    assert "int x = 1 + 2;" in out


def test_object_like_macro_expansion_preserves_token_boundaries(tmp_path):
    # Object-like macro expansion must occur only on identifier tokens.
    # In C, `0A` is not a preprocessing token sequence that contains the
    # identifier token `A`; it's a single pp-number token, so `A` must not
    # be replaced inside it.
    out = _pp_text(
        tmp_path,
        """
        #define A 1 + 2
        int x = 0A0;
        int y = A0;
        int z = 0A;
        int w = A;
        """,
    )

    assert "int x = 0A0;" in out
    assert "int y = A0;" in out
    assert "int z = 0A;" in out
    assert "int w = 1 + 2;" in out
