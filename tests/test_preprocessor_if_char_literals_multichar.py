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


def test_if_multichar_constant_subset_semantics(tmp_path):
    """Multi-character constants are implementation-defined in C.

    Subset semantics for AuraCompiler preprocessor:
    - treat each char as an unsigned byte
    - pack left-to-right in big-endian order into an int

    Examples:
      'AB' == (0x41<<8) | 0x42 == 0x4142
      'ABC' == 0x414243
    """

    out = _pp(
        tmp_path,
        r"""
#if 'AB' == 0x4142
OK_AB
#else
BAD_AB
#endif

#if 'ABC' == 0x414243
OK_ABC
#else
BAD_ABC
#endif
""".lstrip(),
    )

    assert "OK_AB" in out and "BAD_AB" not in out
    assert "OK_ABC" in out and "BAD_ABC" not in out
