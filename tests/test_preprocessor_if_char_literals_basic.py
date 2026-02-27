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


def test_if_char_literals_basic(tmp_path):
    out = _pp(
        tmp_path,
        r"""
#if 'A' == 65
OK_A
#else
BAD_A
#endif

#if '\n' == 10
OK_NL
#else
BAD_NL
#endif

#if '\t' == 9
OK_TAB
#else
BAD_TAB
#endif

#if '\0' == 0
OK_NUL
#else
BAD_NUL
#endif

#if '\\' == 92
OK_BSLASH
#else
BAD_BSLASH
#endif

#if '\'' == 39
OK_SQUOTE
#else
BAD_SQUOTE
#endif
""".lstrip(),
    )

    assert "OK_A" in out and "BAD_A" not in out
    assert "OK_NL" in out and "BAD_NL" not in out
    assert "OK_TAB" in out and "BAD_TAB" not in out
    assert "OK_NUL" in out and "BAD_NUL" not in out
    assert "OK_BSLASH" in out and "BAD_BSLASH" not in out
    assert "OK_SQUOTE" in out and "BAD_SQUOTE" not in out
