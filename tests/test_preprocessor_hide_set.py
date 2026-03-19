import tempfile
from pathlib import Path

from pycc.preprocessor import Preprocessor


def _pp(code: str) -> str:
    # Preprocess with built-in preprocessor only.
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "t.c"
        p.write_text(code)
        pp = Preprocessor(include_paths=[])
        res = pp.preprocess(str(p), initial_macros={})
        assert res.success, "preprocess failed: " + "\n".join(res.errors)
        return res.text


def test_hide_set_object_like_self_recursive_terminates():
    out = _pp(
        r"""
#define A A
A
"""
    )
    # A full C preprocessor leaves a single A; must not infinite-loop.
    assert out.strip() == "A"


def test_hide_set_object_like_mutual_recursion_terminates():
    out = _pp(
        r"""
#define A B
#define B A
A
"""
    )
    # Must terminate; exact fixed point can be either A or B depending on strategy.
    assert out.strip() in {"A", "B"}


def test_hide_set_function_like_self_recursive_terminates():
    out = _pp(
        r"""
#define F(x) F(x)
F(1)
"""
    )
    # Must terminate; should not repeatedly expand.
    assert out.strip() == "F(1)"
