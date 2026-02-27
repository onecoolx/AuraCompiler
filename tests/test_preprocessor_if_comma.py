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


def test_if_comma_basic(tmp_path):
    out = _pp(
        tmp_path,
        """
#if (0, 1)
OK_C1
#else
BAD_C1
#endif

#if (1, 0)
BAD_C2
#else
OK_C2
#endif
""".lstrip(),
    )

    assert "OK_C1" in out and "BAD_C1" not in out
    assert "OK_C2" in out and "BAD_C2" not in out


def test_if_comma_returns_last_value(tmp_path):
    out = _pp(
        tmp_path,
        """
#if (7, 8, 9) == 9
OK_LAST
#else
BAD_LAST
#endif
""".lstrip(),
    )
    assert "OK_LAST" in out and "BAD_LAST" not in out


def test_if_comma_precedence_lowest(tmp_path):
    out = _pp(
        tmp_path,
        """
/* comma has lower precedence than ?: */
#if (0 ? 1 : 2, 3) == 3
OK_PREC
#else
BAD_PREC
#endif
""".lstrip(),
    )
    assert "OK_PREC" in out and "BAD_PREC" not in out
