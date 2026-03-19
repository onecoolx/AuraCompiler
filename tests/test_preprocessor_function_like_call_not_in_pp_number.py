import textwrap

from pycc.preprocessor import Preprocessor


def _pp_text(tmp_path, source_text: str) -> str:
    src = tmp_path / "main.c"
    src.write_text(textwrap.dedent(source_text).lstrip(), encoding="utf-8")
    pp = Preprocessor(include_paths=[str(tmp_path)])
    return pp.preprocess(str(src)).text


def test_function_like_macro_call_does_not_match_inside_pp_number(tmp_path):
    # In preprocessing-token terms, `0F(1)` is a single pp-number token
    # starting with '0', not the identifier token `F` followed by '('.
    out = _pp_text(
        tmp_path,
        """
        #define F(x) x
        int a = 0F(1);
        int b = F(2);
        """,
    )

    assert "int a = 0F(1);" in out
    assert "int b = 2;" in out
