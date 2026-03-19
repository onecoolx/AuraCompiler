import textwrap

from pycc.preprocessor import Preprocessor


def _pp_text(tmp_path, source_text: str) -> str:
    src = tmp_path / "main.c"
    src.write_text(textwrap.dedent(source_text).lstrip(), encoding="utf-8")
    pp = Preprocessor(include_paths=[str(tmp_path)])
    return pp.preprocess(str(src)).text


def test_function_like_recursive_call_in_replacement_does_not_expand_again(tmp_path):
    # F expands to a text that contains a nested F(...) call. That nested call
    # must not be expanded again during the same expansion chain.
    out = _pp_text(
        tmp_path,
        """
        #define F(x) (F(x) + 1)
        int z = F(3);
        """,
    )

    assert "int z = (F(3) + 1);" in out
