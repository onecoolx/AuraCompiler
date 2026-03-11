from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_driver_save_temps_policyB_c_mode(tmp_path: Path):
    c_path = tmp_path / "t.c"
    c_path.write_text("int main(void){return 0;}\n", encoding="utf-8")

    out_o = tmp_path / "out.o"
    r = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "pycc.py"),
            str(c_path),
            "-c",
            "--save-temps",
            "-o",
            str(out_o),
        ],
        cwd=str(tmp_path),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    assert r.returncode == 0, (r.stdout, r.stderr)
    assert out_o.exists()
    # Policy B: keep .i and .s, but do not create pycc-tmp.o in -c mode.
    assert (tmp_path / "pycc-tmp.i").exists()
    assert (tmp_path / "pycc-tmp.s").exists()
    assert not (tmp_path / "pycc-tmp.o").exists()
