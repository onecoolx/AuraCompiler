from __future__ import annotations

import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_driver_dump_ir_writes_file(tmp_path):
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
            "python",
            str(REPO_ROOT / "pycc.py"),
            str(c_path),
            "--dump-ir",
            "-o",
            str(out),
        ],
        cwd=str(tmp_path),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert r.returncode == 0, (r.stdout, r.stderr)
    ir_path = tmp_path / "pycc-tmp.ir"
    assert ir_path.exists()
    txt = ir_path.read_text(encoding="utf-8")
    assert "func_begin" in txt
    assert "ret" in txt
