import textwrap

from pycc.preprocessor import Preprocessor


def _pp_text(tmp_path, source_text):
    src = tmp_path / "main.c"
    src.write_text(textwrap.dedent(source_text).lstrip(), encoding="utf-8")
    pp = Preprocessor(include_paths=[str(tmp_path)])
    return pp.preprocess(str(src)).text


def test_function_like_self_reference_is_bounded(tmp_path):
    out = _pp_text(
        tmp_path,
        """
        #define F(x) F(x)
        int y = F(1);
        """,
    )

    # Subset expectation: no infinite loop; expansion should stabilize.
    assert "int y = F(1);" in out
