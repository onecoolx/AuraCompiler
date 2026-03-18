import textwrap

from pycc.preprocessor import Preprocessor


def _pp_text(tmp_path, source_text):
    src = tmp_path / "main.c"
    src.write_text(textwrap.dedent(source_text).lstrip(), encoding="utf-8")
    pp = Preprocessor(include_paths=[str(tmp_path)])
    return pp.preprocess(str(src)).text


def test_function_like_call_scan_does_not_match_mid_identifier_after_progress(tmp_path):
    out = _pp_text(
        tmp_path,
        """
        #define F(x) x

        // First call expands and advances scanner.
        int a = F(1);
        // If scanning uses substring + \\b, it can incorrectly match the 'F' in 'xF(2)'.
        int b = xF(2);
        int c = F(3);
        """,
    )

    assert "int a = 1;" in out
    assert "int b = xF(2);" in out
    assert "int c = 3;" in out
