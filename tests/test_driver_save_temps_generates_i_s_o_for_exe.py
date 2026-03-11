from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_driver_save_temps_generates_i_s_o_for_executable(tmp_path: Path):
    # In normal compile+link mode, --save-temps should retain stable sidecar
    # files in cwd: preprocessed (.i), assembly (.s), object (.o).
    c_path = tmp_path / "t.c"
    c_path.write_text("int main(void){return 0;}\n", encoding="utf-8")

    out = tmp_path / "a.out"
    r = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "pycc.py"),
            str(c_path),
            "--save-temps",
            "-o",
            str(out),
        ],
        cwd=str(tmp_path),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    assert r.returncode == 0, (r.stdout, r.stderr)
    assert out.exists()
    assert (tmp_path / "pycc-tmp.i").exists()
    assert (tmp_path / "pycc-tmp.s").exists()
    assert (tmp_path / "pycc-tmp.o").exists()
