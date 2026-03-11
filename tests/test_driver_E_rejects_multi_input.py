from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_driver_E_rejects_multi_input(tmp_path: Path):
    a = tmp_path / "a.c"
    b = tmp_path / "b.c"
    a.write_text("int A = 1;\n", encoding="utf-8")
    b.write_text("int B = 2;\n", encoding="utf-8")

    r = subprocess.run(
        [sys.executable, str(REPO_ROOT / "pycc.py"), "-E", str(a), str(b)],
        cwd=str(tmp_path),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    assert r.returncode != 0
    msg = (r.stdout + r.stderr)
    assert "-E" in msg
    assert "exactly one" in msg
