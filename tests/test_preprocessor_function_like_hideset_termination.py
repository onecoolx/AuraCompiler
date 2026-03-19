import textwrap

from pycc.preprocessor import Preprocessor


def _pp_text(tmp_path, source_text: str) -> str:
    src = tmp_path / "main.c"
    src.write_text(textwrap.dedent(source_text).lstrip(), encoding="utf-8")
    pp = Preprocessor(include_paths=[str(tmp_path)])
    return pp.preprocess(str(src)).text


def test_function_like_self_referential_macro_terminates(tmp_path):
    # Subset hide-set behavior: during expansion of F, occurrences of F(...) in
    # its own replacement should not keep expanding and growing.
    out = _pp_text(
        tmp_path,
        """
        #define F(x) F(x) + 1
        int a = F(0);
        """,
    )

    assert "int a = F(0) + 1;" in out
