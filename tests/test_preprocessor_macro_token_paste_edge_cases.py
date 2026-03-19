import tempfile
from pathlib import Path

from pycc.preprocessor import Preprocessor


def _pp(code: str) -> str:
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "t.c"
        p.write_text(code)
        pp = Preprocessor(include_paths=[])
        res = pp.preprocess(str(p), initial_macros={})
        assert res.success, "preprocess failed: " + "\n".join(res.errors)
        return res.text


def test_pp_token_paste_operator_at_start_is_rejected():
    # Standard: '##' may not appear at the beginning or end of replacement list.
    # We choose to reject it with a clear diagnostic (subset).
    code = r"""
#define A(x) ##x
A(1)
"""
    try:
        _pp(code)
        assert False, "expected preprocess to fail"
    except AssertionError as e:
        # _pp asserts on PreprocessResult.success; check the diagnostic text.
        msg = str(e)
        assert "##" in msg
        assert "start" in msg.lower() or "begin" in msg.lower()


def test_pp_token_paste_operator_at_end_is_rejected():
    code = r"""
#define B(x) x##
B(1)
"""
    try:
        _pp(code)
        assert False, "expected preprocess to fail"
    except AssertionError as e:
        msg = str(e)
        assert "##" in msg
        assert "end" in msg.lower()
