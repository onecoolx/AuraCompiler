from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_driver_multi_input_rejects_stdin_dash(tmp_path: Path):
    # Multi-input mode currently expects real source paths. Ensure using '-' as one
    # of the inputs is rejected with a clear error.
    a = tmp_path / "a.c"
    b = tmp_path / "b.c"
    a.write_text("int a(void){ return 1; }\n", encoding="utf-8")
    b.write_text("int main(void){ return a(); }\n", encoding="utf-8")

    out = tmp_path / "a.out"
    r = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "pycc.py"),
            str(a),
            "-",
            str(b),
            "-o",
            str(out),
        ],
        cwd=str(tmp_path),
        input="int dummy(void){return 0;}\n",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    assert r.returncode != 0
    assert "-" in (r.stdout + r.stderr)
