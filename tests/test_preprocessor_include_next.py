import subprocess
import sys
from pathlib import Path


def test_preprocessor_E_include_next_is_rejected(tmp_path: Path):
    repo_root = Path(__file__).resolve().parents[1]

    src = tmp_path / "t.c"
    src.write_text(
        r"""
#include_next <stdio.h>
int main(void){ return 0; }
""".lstrip()
    )

    p = subprocess.run(
        [sys.executable, "pycc.py", "-E", str(src)],
        cwd=str(repo_root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert p.returncode != 0
    msg = (p.stdout + p.stderr).lower()
    assert "include_next" in msg
    assert "unsupported" in msg
