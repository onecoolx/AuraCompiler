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


def test_if_hex_literals(tmp_path):
    out = _pp(
        tmp_path,
        """
#if 0x10 == 16
OK_HEX1
#else
BAD_HEX1
#endif

#if 0x2a == 42
OK_HEX2
#else
BAD_HEX2
#endif

#if (0x10 + 0x1) == 17
OK_HEX3
#else
BAD_HEX3
#endif
""".lstrip(),
    )
    assert "OK_HEX1" in out and "BAD_HEX1" not in out
    assert "OK_HEX2" in out and "BAD_HEX2" not in out
    assert "OK_HEX3" in out and "BAD_HEX3" not in out


def test_if_octal_literals(tmp_path):
    out = _pp(
        tmp_path,
        """
#if 010 == 8
OK_OCT1
#else
BAD_OCT1
#endif

#if (010 + 1) == 9
OK_OCT2
#else
BAD_OCT2
#endif
""".lstrip(),
    )
    assert "OK_OCT1" in out and "BAD_OCT1" not in out
    assert "OK_OCT2" in out and "BAD_OCT2" not in out
