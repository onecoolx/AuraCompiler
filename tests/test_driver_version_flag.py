from __future__ import annotations

import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_driver_version_flag():
    r = subprocess.run(
        ["python", str(REPO_ROOT / "pycc.py"), "--version"],
        cwd=str(REPO_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert r.returncode == 0, (r.stdout, r.stderr)
    assert "pycc" in r.stdout.lower()
