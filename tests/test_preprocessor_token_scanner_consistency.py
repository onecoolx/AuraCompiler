import textwrap

from pycc.preprocessor import Preprocessor


def _pp_text(tmp_path, source_text: str) -> str:
    src = tmp_path / "main.c"
    src.write_text(textwrap.dedent(source_text).lstrip(), encoding="utf-8")
    pp = Preprocessor(include_paths=[str(tmp_path)])
    return pp.preprocess(str(src)).text


def test_token_boundaries_are_consistent_across_expanders(tmp_path):
    # This test is meant to stress that both object-like and function-like
    # expansion should agree on what is a token boundary (strings/chars,
    # pp-numbers, etc.).
    out = _pp_text(
        tmp_path,
        r"""
        #define A 7
        #define F(x) x

        int a = 0A;      // A inside pp-number should not expand
        int b = F(0A);   // same
        int c = A;       // should expand
        int d = F(A);    // should expand

        const char* s = "A F(A) 0A";
        """,
    )

    assert "int a = 0A;" in out
    assert "int b = 0A;" in out
    assert "int c = 7;" in out
    assert "int d = 7;" in out
    assert 'const char* s = "A F(A) 0A";' in out
