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


def test_macro_not_reexpanded_within_its_own_replacement_list(tmp_path):
    # In C, during expansion of A, the macro name A is disabled for rescanning
    # its own replacement list.
    out = _pp(
        tmp_path,
        """
#define A A + 1
A
""".lstrip(),
    )
    # Expect exactly one expansion: A -> A + 1, but that inner A should not
    # expand again as part of the same replacement list rescan.
    assert out.strip() == "A + 1"


def test_macro_reenabled_after_expansion_boundary(tmp_path):
    # A is disabled only while expanding A; once the expansion finishes, A may be
    # expanded again if it appears from other sources.
    out = _pp(
        tmp_path,
        """
#define A A + 1
#define WRAP(x) x
WRAP(A)
""".lstrip(),
    )
    # WRAP expands to A, and then A expands once, yielding A + 1.
    assert out.strip() == "A + 1"
