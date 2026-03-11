from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_driver_save_temps_retains_dump_files(tmp_path: Path):
    # When --save-temps is enabled, debug dump files should be written into cwd
    # (stable names) rather than being tied to internal temp locations.
    c_path = tmp_path / "t.c"
    c_path.write_text(
        """
int main(void){ return 0; }
""".lstrip(),
        encoding="utf-8",
    )

    out = tmp_path / "a.out"
    r = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "pycc.py"),
            str(c_path),
            "--save-temps",
            "--dump-preprocessed",
            "--dump-ir",
            "--dump-asm",
            "--dump-tokens",
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
    assert (tmp_path / "pycc-tmp.ir").exists()
    assert (tmp_path / "pycc-tmp.s").exists()
    assert (tmp_path / "pycc-tmp.tokens").exists()
