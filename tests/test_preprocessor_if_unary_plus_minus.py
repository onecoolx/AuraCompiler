import os
import subprocess
import sys


def _pp(tmp_path, src: str) -> str:
    p = tmp_path / "t.c"
    p.write_text(src, encoding="utf-8")
    r = subprocess.run(
        [sys.executable, os.fspath(os.path.join(os.getcwd(), "pycc.py")), "-E", os.fspath(p)],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, (r.stdout, r.stderr)
    return r.stdout


def test_if_unary_plus_minus_basic(tmp_path):
    out = _pp(
        tmp_path,
        """
#if (+1) == 1
OK_P1
#else
BAD_P1
#endif

#if (-1) == -1
OK_M1
#else
BAD_M1
#endif

#if (-(-3)) == 3
OK_DBL
#else
BAD_DBL
#endif
""".lstrip(),
    )
    assert "OK_P1" in out and "BAD_P1" not in out
    assert "OK_M1" in out and "BAD_M1" not in out
    assert "OK_DBL" in out and "BAD_DBL" not in out


def test_if_unary_plus_minus_precedence_and_composition(tmp_path):
    out = _pp(
        tmp_path,
        """
/* unary binds tighter than shifts */
#if (-1 << 1) == ((-1) << 1)
OK_PREC1
#else
BAD_PREC1
#endif

/* composition with ~ */
#if (-~1) == 2
OK_COMP1
#else
BAD_COMP1
#endif

#if (~-1) == 0
OK_COMP2
#else
BAD_COMP2
#endif

/* parentheses with shifts */
#if (-(1 << 2)) == -4
OK_PAREN
#else
BAD_PAREN
#endif
""".lstrip(),
    )
    assert "OK_PREC1" in out and "BAD_PREC1" not in out
    assert "OK_COMP1" in out and "BAD_COMP1" not in out
    assert "OK_COMP2" in out and "BAD_COMP2" not in out
    assert "OK_PAREN" in out and "BAD_PAREN" not in out
