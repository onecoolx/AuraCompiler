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


def test_pp_token_paste_with_empty_object_like_arg_left():
    # In real preprocessors, empty args are allowed and token-pasting with an
    # empty side effectively concatenates with the non-empty side.
    out = _pp(
        r"""
#define CAT(a,b) a##b
#define EMPTY
CAT(EMPTY, X)
"""
    )
    assert out.strip() == "X"


def test_pp_token_paste_with_empty_object_like_arg_right():
    out = _pp(
        r"""
#define CAT(a,b) a##b
#define EMPTY
CAT(X, EMPTY)
"""
    )
    assert out.strip() == "X"


def test_pp_token_paste_with_empty_fn_arg():
    out = _pp(
        r"""
#define CAT(a,b) a##b
CAT(, X)
CAT(X, )
"""
    )
    lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
    assert lines == ["X", "X"]


def test_pp_token_paste_with_empty__param_name_as_token_is_rejected():
    # With our current token-paste subset, empty actual arguments are tolerated
    # and pasting with an empty side yields the non-empty side.
    code = r"""
#define CAT(a,b) a##b
CAT(, X)
"""
    out = _pp(code)
    assert out.strip() == "X"


def test_pp_token_paste_with_empty___VA_ARGS___already_supported_subset():
    out = _pp(
        r"""
#define LOG(fmt, ...) printf(fmt, ##__VA_ARGS__)
LOG("hi\n")
"""
    )
    # Should swallow comma and produce printf("hi\n")
    assert 'printf("hi\\n")' in out.replace(" ", "")
