import os
import subprocess
import sys
import tempfile
from pathlib import Path

from pycc.preprocessor import Preprocessor


def test_E_include_cycle_has_file_line(tmp_path: Path):
    # t.c includes a.h; a.h includes a.h (cycle) -> should report a.h:1
    (tmp_path / "a.h").write_text('#include "a.h"\n')
    (tmp_path / "t.c").write_text('#include "a.h"\n')

    r = subprocess.run(
        [sys.executable, "pycc.py", "-E", str(tmp_path / "t.c"), "-I", str(tmp_path)],
        cwd=Path(__file__).resolve().parents[1],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert r.returncode != 0
    msg = (r.stdout + r.stderr)
    assert "a.h" in msg
    assert ":1" in msg


def test_pp_cannot_read_file_has_file_line():
    # Direct PP call on missing file should produce <file>:1: cannot read ...
    pp = Preprocessor(include_paths=[])
    missing = os.path.join(tempfile.gettempdir(), "definitely_missing_file_abcxyz.c")
    try:
        os.unlink(missing)
    except OSError:
        pass
    res = pp.preprocess(missing, initial_macros={})
    assert not res.success
    msg = "\n".join(res.errors)
    assert "definitely_missing_file_abcxyz.c" in msg
    assert ":1" in msg
    assert "cannot read" in msg.lower()


def test_E_unsupported_macro_invocation_has_file_line(tmp_path: Path):
    # Wrong arity in function-like macro invocation.
    (tmp_path / "t.c").write_text(
        """
#define F(a,b) a+b
int x = F(1);
""".lstrip()
    )
    r = subprocess.run(
        [sys.executable, "pycc.py", "-E", str(tmp_path / "t.c")],
        cwd=Path(__file__).resolve().parents[1],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert r.returncode != 0
    msg = (r.stdout + r.stderr)
    assert "t.c" in msg
    assert ":2" in msg
    assert "expects" in msg.lower()


def test_E_unsupported_if_expression_has_file_line(tmp_path: Path):
    # Trigger a known unsupported #if expression error.
    (tmp_path / "t.c").write_text(
        """
#if 1/0
int x;
#endif
""".lstrip()
    )
    r = subprocess.run(
        [sys.executable, "pycc.py", "-E", str(tmp_path / "t.c")],
        cwd=Path(__file__).resolve().parents[1],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert r.returncode != 0
    msg = (r.stdout + r.stderr)
    assert "t.c" in msg
    assert ":1" in msg
    assert "unsupported" in msg.lower()
