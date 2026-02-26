import subprocess
import sys
from pathlib import Path


def test_preprocessor_E_pragma_once_is_ignored(tmp_path: Path):
    repo_root = Path(__file__).resolve().parents[1]

    src = tmp_path / "t.c"
    src.write_text(
        r"""
#pragma once
int x = 1;
""".lstrip()
    )

    p = subprocess.run(
        [sys.executable, "pycc.py", "-E", str(src)],
        cwd=str(repo_root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert p.returncode == 0, p.stdout + p.stderr
    assert "#pragma once" not in p.stdout
    assert "int x = 1;" in p.stdout
