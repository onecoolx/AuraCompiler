from __future__ import annotations

import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_driver_v_prints_compile_action(tmp_path):
    c_path = tmp_path / "t.c"
    c_path.write_text(
        """
int main(void) { return 0; }
""".lstrip(),
        encoding="utf-8",
    )

    out_s = tmp_path / "out.s"
    r = subprocess.run(
        ["python", str(REPO_ROOT / "pycc.py"), str(c_path), "-S", "-v", "-o", str(out_s)],
        cwd=str(tmp_path),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert r.returncode == 0, (r.stdout, r.stderr)
    assert "[pycc] compile:" in r.stdout
    assert out_s.exists()
