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


def test_if_unary_bitwise_not_basic(tmp_path):
    out = _pp(
        tmp_path,
        """
#if (~0) == -1
OK_NOT1
#else
BAD_NOT1
#endif

#if (~1) == -2
OK_NOT2
#else
BAD_NOT2
#endif
""".lstrip(),
    )
    assert "OK_NOT1" in out and "BAD_NOT1" not in out
    assert "OK_NOT2" in out and "BAD_NOT2" not in out


def test_if_unary_bitwise_not_precedence(tmp_path):
    out = _pp(
        tmp_path,
        """
/* unary binds tighter than shifts */
#if (~1 << 1) == ((~1) << 1)
OK_PREC1
#else
BAD_PREC1
#endif

/* parentheses still work */
#if (~(1 << 1)) == (~2)
OK_PREC2
#else
BAD_PREC2
#endif
""".lstrip(),
    )
    assert "OK_PREC1" in out and "BAD_PREC1" not in out
    assert "OK_PREC2" in out and "BAD_PREC2" not in out
