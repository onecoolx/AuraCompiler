from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_driver_E_stdout_matches_o_file(tmp_path: Path):
    src = tmp_path / "t.c"
    src.write_text(
        r"""
#define X 123
int x = X;
""".lstrip(),
        encoding="utf-8",
    )

    # -E to stdout
    r1 = subprocess.run(
        [sys.executable, str(REPO_ROOT / "pycc.py"), "-E", str(src)],
        cwd=str(tmp_path),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert r1.returncode == 0, r1.stderr

    # -E to file
    out_i = tmp_path / "out.i"
    r2 = subprocess.run(
        [sys.executable, str(REPO_ROOT / "pycc.py"), "-E", str(src), "-o", str(out_i)],
        cwd=str(tmp_path),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert r2.returncode == 0, r2.stderr
    assert out_i.exists()

    assert r1.stdout == out_i.read_text(encoding="utf-8")
