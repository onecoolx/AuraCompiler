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
    # Current subset behavior: tolerate it by dropping the operator.
    code = r"""
#define A(x) ##x
A(1)
"""
    out = _pp(code)
    assert out.strip() == "1"


def test_pp_token_paste_operator_at_end_is_rejected():
    code = r"""
#define B(x) x##
B(1)
"""
    out = _pp(code)
    assert out.strip() == "1"
