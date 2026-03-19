import textwrap

from pycc.preprocessor import Preprocessor


def _pp_text(tmp_path, source_text: str) -> str:
    src = tmp_path / "main.c"
    src.write_text(textwrap.dedent(source_text).lstrip(), encoding="utf-8")
    pp = Preprocessor(include_paths=[str(tmp_path)])
    return pp.preprocess(str(src)).text


def test_function_like_macro_not_invoked_from_comment_text(tmp_path):
    # Comments are removed before macro expansion; ensure we don't accidentally
    # treat comment text as macro calls.
    out = _pp_text(
        tmp_path,
        """
        #define F(x) x
        // F(1)
        int a = F(2);
        /* F(3) */
        int b = F(4);
        """,
    )

    assert "int a = 2;" in out
    assert "int b = 4;" in out
