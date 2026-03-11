from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_driver_missing_input_with_o_reports_error(tmp_path: Path):
    # Basic UX check: even if -o is provided, missing input should be an error.
    out = tmp_path / "a.out"
    r = subprocess.run(
        [sys.executable, str(REPO_ROOT / "pycc.py"), "-o", str(out)],
        cwd=str(tmp_path),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert r.returncode != 0
    msg = (r.stdout + r.stderr).lower()
    assert "missing input" in msg
