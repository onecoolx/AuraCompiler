import os
import subprocess
import sys
import tempfile
from pathlib import Path

from pycc.preprocessor import Preprocessor


def test_pp_error_message_includes_file_and_line():
    # Use the Preprocessor API directly to check the raw diagnostic string.
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        p = td / "t.c"
        p.write_text("\n\n#error boom\n")
        pp = Preprocessor(include_paths=[])
        res = pp.preprocess(str(p), initial_macros={})
        assert not res.success
        msg = "\n".join(res.errors)
        assert "t.c" in msg
        assert ":3" in msg  # line 3


def test_E_error_message_includes_file_and_line(tmp_path: Path):
    c_path = tmp_path / "t.c"
    c_path.write_text("\n\n#error boom\n")
    r = subprocess.run(
        [sys.executable, "pycc.py", "-E", str(c_path)],
        cwd=Path(__file__).resolve().parents[1],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert r.returncode != 0
    msg = (r.stdout + r.stderr)
    assert "t.c" in msg
    assert ":3" in msg


def test_E_missing_include_includes_includer_location_and_stack(tmp_path: Path):
    # a.h includes missing b.h; expect error points at a.h:1 and stack includes t.c -> a.h
    (tmp_path / "a.h").write_text('#include "b.h"\n')
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
    assert "include stack" in msg.lower()
    assert "t.c" in msg

