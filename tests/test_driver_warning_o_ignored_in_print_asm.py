from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_driver_print_asm_with_o_does_not_create_output_file(tmp_path: Path):
    c_path = tmp_path / "t.c"
    c_path.write_text("int main(void){return 0;}\n", encoding="utf-8")

    out_s = tmp_path / "out.s"
    r = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "pycc.py"),
            str(c_path),
            "--print-asm",
            "-o",
            str(out_s),
        ],
        cwd=str(tmp_path),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    assert r.returncode == 0, (r.stdout, r.stderr)
    assert ".text" in r.stdout
    # --print-asm prints to stdout; -o should not create the requested file.
    assert not out_s.exists()
