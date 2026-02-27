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


def test_if_bitwise_and_or_xor_not(tmp_path):
    out = _pp(
        tmp_path,
        """
#if (1 & 3) == 1
OK_AND
#else
BAD_AND
#endif

#if (1 | 2) == 3
OK_OR
#else
BAD_OR
#endif

#if (5 ^ 1) == 4
OK_XOR
#else
BAD_XOR
#endif

#if (~0) < 0
OK_NOT
#else
BAD_NOT
#endif
""".lstrip(),
    )

    assert "OK_AND" in out and "BAD_AND" not in out
    assert "OK_OR" in out and "BAD_OR" not in out
    assert "OK_XOR" in out and "BAD_XOR" not in out
    assert "OK_NOT" in out and "BAD_NOT" not in out


def test_if_shifts_and_precedence(tmp_path):
    out = _pp(
        tmp_path,
        """
#if (1 << 3) == 8
OK_SHL
#else
BAD_SHL
#endif

#if (8 >> 2) == 2
OK_SHR
#else
BAD_SHR
#endif

/* precedence: shifts bind tighter than &: 1 << 2 & 1 == (1<<2) & 1 == 4 & 1 == 0 */
#if (1 << 2 & 1) == 0
OK_PREC1
#else
BAD_PREC1
#endif

/* precedence: & binds tighter than ^, which binds tighter than | */
#if (1 | 2 ^ 3 & 1) == (1 | (2 ^ (3 & 1)))
OK_PREC2
#else
BAD_PREC2
#endif
""".lstrip(),
    )

    assert "OK_SHL" in out and "BAD_SHL" not in out
    assert "OK_SHR" in out and "BAD_SHR" not in out
    assert "OK_PREC1" in out and "BAD_PREC1" not in out
    assert "OK_PREC2" in out and "BAD_PREC2" not in out
