from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_driver_save_temps_policyB_S_mode(tmp_path: Path):
    c_path = tmp_path / "t.c"
    c_path.write_text("int main(void){return 0;}\n", encoding="utf-8")

    out_s = tmp_path / "out.s"
    r = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "pycc.py"),
            str(c_path),
            "-S",
            "--save-temps",
            "-o",
            str(out_s),
        ],
        cwd=str(tmp_path),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    assert r.returncode == 0, (r.stdout, r.stderr)
    assert out_s.exists()
    # Policy B: keep .i, but do not create redundant pycc-tmp.s in -S mode.
    assert (tmp_path / "pycc-tmp.i").exists()
    assert not (tmp_path / "pycc-tmp.s").exists()
    assert not (tmp_path / "pycc-tmp.o").exists()
