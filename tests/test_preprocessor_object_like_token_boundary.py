import textwrap

from pycc.preprocessor import Preprocessor


def _pp_text(tmp_path, source_text: str) -> str:
    src = tmp_path / "main.c"
    src.write_text(textwrap.dedent(source_text).lstrip(), encoding="utf-8")
    pp = Preprocessor(include_paths=[str(tmp_path)])
    return pp.preprocess(str(src)).text


def test_object_like_macro_does_not_expand_inside_longer_identifier(tmp_path):
    out = _pp_text(
        tmp_path,
        """
        #define A 1
        int AB = 2;
        int x = A + AB;
        """,
    )

    assert "int AB = 2;" in out
    assert "int x = 1 + AB;" in out


def test_object_like_macro_does_not_expand_inside_comment(tmp_path):
    out = _pp_text(
        tmp_path,
        r"""
        #define A 1
        // A should not expand here
        int x = A;
        /* A should not expand here either */
        int y = A;
        """,
    )

    # This preprocessor strips comments from output (subset).
    assert "int x = 1;" in out
    assert "int y = 1;" in out


def test_object_like_macro_not_expanded_in_header_name_tokens(tmp_path):
    # Header-name tokens are special in a real preprocessor. As a minimal
    # subset we require we don't rewrite inside the quoted file name.
    (tmp_path / "A.h").write_text("#define Z 9\n", encoding="utf-8")

    out = _pp_text(
        tmp_path,
        """
        #define A 1
        #include "A.h"
        int z = Z;
        """,
    )

    assert "int z = 9;" in out
