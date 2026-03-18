import textwrap

from pycc.preprocessor import Preprocessor


def _pp_text(tmp_path, source_text):
    src = tmp_path / "main.c"
    src.write_text(textwrap.dedent(source_text).lstrip(), encoding="utf-8")
    pp = Preprocessor(include_paths=[str(tmp_path)])
    return pp.preprocess(str(src)).text


def test_function_like_param_not_substituted_inside_string_literal(tmp_path):
    out = _pp_text(
        tmp_path,
        r"""
        #define M(x) "x" x
        int a = 1;
        int b = M(7);
        """,
    )

    # "x" must remain literal, only the identifier token x becomes 7.
    assert '"x" 7' in out
