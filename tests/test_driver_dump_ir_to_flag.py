from __future__ import annotations

import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_driver_dump_ir_to_writes_requested_path(tmp_path: Path):
    c_path = tmp_path / "t.c"
    c_path.write_text(
        """
int main(void){ return 0; }
""".lstrip(),
        encoding="utf-8",
    )

    out = tmp_path / "a.out"
    out_ir = tmp_path / "custom.ir"
    r = subprocess.run(
        [
            "python",
            str(REPO_ROOT / "pycc.py"),
            str(c_path),
            "--dump-ir-to",
            str(out_ir),
            "-o",
            str(out),
        ],
        cwd=str(tmp_path),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert r.returncode == 0, (r.stdout, r.stderr)
    assert out_ir.exists()
    txt = out_ir.read_text(encoding="utf-8")
    assert "func_begin" in txt
    assert out.exists()
