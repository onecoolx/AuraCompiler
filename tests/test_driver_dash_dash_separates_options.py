from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_driver_double_dash_separates_options_from_files(tmp_path: Path):
    # Ensure `--` works like common gcc/clang convention: it ends option parsing
    # so a file named "-" can be passed literally.
    #
    # Here we create a file literally named "-" and compile it.
    dash_file = tmp_path / "-"
    dash_file.write_text(
        """
int main(void){ return 0; }
""".lstrip(),
        encoding="utf-8",
    )

    out = tmp_path / "a.out"
    r = subprocess.run(
        [sys.executable, str(REPO_ROOT / "pycc.py"), str(dash_file), "-o", str(out)],
        cwd=str(tmp_path),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    assert r.returncode == 0, (r.stdout, r.stderr)
    assert out.exists()
