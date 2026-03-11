from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_driver_no_args_prints_missing_input_error():
    r = subprocess.run(
        [sys.executable, str(REPO_ROOT / "pycc.py")],
        cwd=str(REPO_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert r.returncode != 0
    txt = (r.stdout + r.stderr).lower()
    assert "missing input" in txt
