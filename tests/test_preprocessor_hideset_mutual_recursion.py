import textwrap

from pycc.preprocessor import Preprocessor


def _pp_text(tmp_path, source_text: str) -> str:
    src = tmp_path / "main.c"
    src.write_text(textwrap.dedent(source_text).lstrip(), encoding="utf-8")
    pp = Preprocessor(include_paths=[str(tmp_path)])
    return pp.preprocess(str(src)).text


def test_object_like_mutual_recursion_terminates_without_growth(tmp_path):
    out = _pp_text(
        tmp_path,
        """
        #define A B
        #define B A
        int x = A;
        """,
    )

    # Must terminate; the exact stabilized result in this subset is acceptable
    # as long as it doesn't grow or crash.
    assert "int x = A;" in out or "int x = B;" in out


def test_function_like_mutual_recursion_terminates_without_growth(tmp_path):
    out = _pp_text(
        tmp_path,
        """
        #define F(x) G(x)
        #define G(x) F(x)
        int y = F(1);
        """,
    )

    assert "int y = F(1);" in out or "int y = G(1);" in out
