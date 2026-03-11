from __future__ import annotations

import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_driver_compile_from_stdin(tmp_path):
    # gcc-style: '-' as input file means stdin.
    src = "int main(void){ return 0; }\n"
    out = tmp_path / "a.out"
    r = subprocess.run(
        ["python", str(REPO_ROOT / "pycc.py"), "-", "-o", str(out)],
        cwd=str(tmp_path),
        input=src,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert r.returncode == 0, (r.stdout, r.stderr)
    rr = subprocess.run([str(out)])
    assert rr.returncode == 0
