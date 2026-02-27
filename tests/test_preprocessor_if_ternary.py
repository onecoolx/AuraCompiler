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


def test_if_ternary_basic(tmp_path):
    out = _pp(
        tmp_path,
        """
#if (1 ? 11 : 22) == 11
OK_T1
#else
BAD_T1
#endif

#if (0 ? 11 : 22) == 22
OK_T2
#else
BAD_T2
#endif
""".lstrip(),
    )
    assert "OK_T1" in out and "BAD_T1" not in out
    assert "OK_T2" in out and "BAD_T2" not in out


def test_if_ternary_precedence_vs_logical(tmp_path):
    out = _pp(
        tmp_path,
        """
/* ?: has lower precedence than || */
#if (0 || 1 ? 3 : 4) == 3
OK_PREC1
#else
BAD_PREC1
#endif

/* ?: has lower precedence than && */
#if (1 && 0 ? 3 : 4) == 4
OK_PREC2
#else
BAD_PREC2
#endif
""".lstrip(),
    )
    assert "OK_PREC1" in out and "BAD_PREC1" not in out
    assert "OK_PREC2" in out and "BAD_PREC2" not in out


def test_if_ternary_right_associative(tmp_path):
    out = _pp(
        tmp_path,
        """
/* right associative: 1 ? 2 : 3 ? 4 : 5 == 2 */
#if (1 ? 2 : 3 ? 4 : 5) == 2
OK_ASSOC1
#else
BAD_ASSOC1
#endif

/* right associative: 0 ? 2 : 3 ? 4 : 5 == (0?2:(3?4:5)) == 4 */
#if (0 ? 2 : 3 ? 4 : 5) == 4
OK_ASSOC2
#else
BAD_ASSOC2
#endif
""".lstrip(),
    )
    assert "OK_ASSOC1" in out and "BAD_ASSOC1" not in out
    assert "OK_ASSOC2" in out and "BAD_ASSOC2" not in out
