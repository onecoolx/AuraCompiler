from pycc.preprocessor import Preprocessor


def _pp(code: str) -> str:
    import tempfile
    from pathlib import Path

    # Preprocess with built-in preprocessor only.
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "t.c"
        p.write_text(code)
        pp = Preprocessor(include_paths=[])
        res = pp.preprocess(str(p), initial_macros={})
        assert res.success, "preprocess failed: " + "\n".join(res.errors)
        return res.text


def test_pp_if_expr_operator_precedence_and_shift():
    code = r"""
#if 1 || 0 && 0
int x = 1;
#else
int x = 2;
#endif

#if (1<<3) == 8
int y = 3;
#else
int y = 4;
#endif
"""
    out = _pp(code)
    assert "int x = 1;" in out
    assert "int y = 3;" in out


def test_pp_if_expr_hex_and_octal_literals():
    code = r"""
#if 0x10 + 010 == 24
int ok = 1;
#else
int ok = 0;
#endif
"""
    out = _pp(code)
    assert "int ok = 1;" in out


def test_pp_if_expr_char_constant_basic():
    # C89: character constants are int.
    code = r"""
#if 'A' == 65
int ok = 1;
#else
int ok = 0;
#endif
"""
    out = _pp(code)
    assert "int ok = 1;" in out
