from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_driver_help_flag_exits_zero():
    r = subprocess.run(
        [sys.executable, str(REPO_ROOT / "pycc.py"), "-h"],
        cwd=str(REPO_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert r.returncode == 0
    # argparse help typically goes to stdout.
    txt = (r.stdout + r.stderr).lower()
    assert "usage" in txt
    assert "pycc" in txt
