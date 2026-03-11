from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_driver_dump_preprocessed_only_to_writes_and_exits(tmp_path: Path):
    src = tmp_path / "t.c"
    src.write_text(
        """
#define X 9
int main(void){ return X; }
""".lstrip(),
        encoding="utf-8",
    )

    out_i = tmp_path / "only.i"
    out = tmp_path / "a.out"

    r = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "pycc.py"),
            "--dump-preprocessed-only-to",
            str(out_i),
            str(src),
            "-o",
            str(out),
        ],
        cwd=str(tmp_path),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    assert r.returncode == 0, (r.stdout, r.stderr)
    assert out_i.exists()
    assert "9" in out_i.read_text(encoding="utf-8")
    # Should stop after dumping, not producing the executable.
    assert not out.exists()
