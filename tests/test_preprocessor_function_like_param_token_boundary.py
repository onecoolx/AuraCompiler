import textwrap

from pycc.preprocessor import Preprocessor


def _pp_text(tmp_path, source_text):
    src = tmp_path / "main.c"
    src.write_text(textwrap.dedent(source_text).lstrip(), encoding="utf-8")
    pp = Preprocessor(include_paths=[str(tmp_path)])
    return pp.preprocess(str(src)).text


def test_function_like_param_substitution_is_token_based(tmp_path):
    out = _pp_text(
        tmp_path,
        """
        #define M(P) P + P1
        int x = M(7);
        """,
    )

    # Only the token P should substitute; P1 must remain P1.
    assert "int x = 7 + P1;" in out
