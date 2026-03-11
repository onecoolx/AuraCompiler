from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_driver_E_accepts_stdin_dash(tmp_path: Path):
    src_text = """
#define X 42
int x = X;
""".lstrip()

    r = subprocess.run(
        [sys.executable, str(REPO_ROOT / "pycc.py"), "-E", "-"],
        cwd=str(tmp_path),
        input=src_text,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert r.returncode == 0, (r.stdout, r.stderr)
    assert "42" in r.stdout
