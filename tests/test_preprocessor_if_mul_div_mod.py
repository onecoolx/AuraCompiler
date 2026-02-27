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


def test_if_mul_div_mod_basic(tmp_path):
    out = _pp(
        tmp_path,
        """
#if 2 * 3 == 6
OK_MUL
#else
BAD_MUL
#endif

#if 8 / 2 == 4
OK_DIV
#else
BAD_DIV
#endif

#if 8 % 3 == 2
OK_MOD
#else
BAD_MOD
#endif
""".lstrip(),
    )

    assert "OK_MUL" in out and "BAD_MUL" not in out
    assert "OK_DIV" in out and "BAD_DIV" not in out
    assert "OK_MOD" in out and "BAD_MOD" not in out


def test_if_mul_div_mod_precedence(tmp_path):
    out = _pp(
        tmp_path,
        """
/* precedence: * binds tighter than + */
#if 1 + 2 * 3 == 7
OK_PREC_MUL
#else
BAD_PREC_MUL
#endif

/* precedence: multiplicative binds tighter than shifts */
#if (1 << 4) / 2 == 8
OK_PREC_DIV
#else
BAD_PREC_DIV
#endif

/* precedence: multiplicative binds tighter than bitwise and */
#if (6 & 3) == 2
OK_SANITY_AND
#else
BAD_SANITY_AND
#endif
#if (6 & 3) * 2 == 4
OK_PREC_AND
#else
BAD_PREC_AND
#endif
""".lstrip(),
    )

    assert "OK_PREC_MUL" in out and "BAD_PREC_MUL" not in out
    assert "OK_PREC_DIV" in out and "BAD_PREC_DIV" not in out
    assert "OK_SANITY_AND" in out and "BAD_SANITY_AND" not in out
    assert "OK_PREC_AND" in out and "BAD_PREC_AND" not in out
