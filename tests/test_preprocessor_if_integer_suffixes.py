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


def test_pp_if_integer_literal_suffix_U_and_L():
    code = r"""
#if 0u
int a = 1;
#else
int a = 2;
#endif

#if 1UL
int b = 3;
#else
int b = 4;
#endif

#if 0x10uL == 16
int c = 5;
#else
int c = 6;
#endif
"""
    out = _pp(code)
    assert "int a = 2;" in out
    assert "int b = 3;" in out
    assert "int c = 5;" in out
