from __future__ import annotations

import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_driver_default_output_a_out(tmp_path):
    c_path = tmp_path / "t.c"
    c_path.write_text(
        """
int main(void) { return 0; }
""".lstrip(),
        encoding="utf-8",
    )

    # No -o, no -S/-c -> a.out in current working directory.
    r = subprocess.run(
        ["python", str(REPO_ROOT / "pycc.py"), str(c_path)],
        cwd=str(tmp_path),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert r.returncode == 0, (r.stdout, r.stderr)
    assert (tmp_path / "a.out").exists()

    rr = subprocess.run([str(tmp_path / "a.out")])
    assert rr.returncode == 0
