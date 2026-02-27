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


def test_if_char_literals_hex_escape(tmp_path):
    out = _pp(
        tmp_path,
        r"""
#if '\x41' == 65
OK_X1
#else
BAD_X1
#endif

#if '\x0a' == 10
OK_X2
#else
BAD_X2
#endif
""".lstrip(),
    )
    assert "OK_X1" in out and "BAD_X1" not in out
    assert "OK_X2" in out and "BAD_X2" not in out


def test_if_char_literals_octal_escape(tmp_path):
    out = _pp(
        tmp_path,
        r"""
#if '\101' == 65
OK_O1
#else
BAD_O1
#endif

#if '\012' == 10
OK_O2
#else
BAD_O2
#endif
""".lstrip(),
    )
    assert "OK_O1" in out and "BAD_O1" not in out
    assert "OK_O2" in out and "BAD_O2" not in out


def test_if_char_literals_octal_escape_short_forms(tmp_path):
    out = _pp(
        tmp_path,
        r"""
#if '\12' == 10
OK_OS1
#else
BAD_OS1
#endif

#if '\0' == 0
OK_OS2
#else
BAD_OS2
#endif
""".lstrip(),
    )
    assert "OK_OS1" in out and "BAD_OS1" not in out
    assert "OK_OS2" in out and "BAD_OS2" not in out
