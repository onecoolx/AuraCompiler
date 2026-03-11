from __future__ import annotations

import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_driver_print_asm_flag(tmp_path):
    c_path = tmp_path / "t.c"
    c_path.write_text(
        """
int main(void) { return 0; }
""".lstrip(),
        encoding="utf-8",
    )

    r = subprocess.run(
        ["python", str(REPO_ROOT / "pycc.py"), str(c_path), "--print-asm"],
        cwd=str(tmp_path),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert r.returncode == 0, (r.stdout, r.stderr)
    assert ".text" in r.stdout
    # In this mode we should not leave a default output file behind.
    assert not (tmp_path / "a.out").exists()
