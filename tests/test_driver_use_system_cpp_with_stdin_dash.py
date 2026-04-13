from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_driver_use_system_cpp_with_stdin_dash(tmp_path: Path):
    if shutil.which("gcc") is None:
        pytest.skip("gcc not available")

    # Ensure stdin input works the same way as a file input when using system cpp.
    src_text = """
#include <stdio.h>
int main(void){ printf(\"hi\\n\"); return 0; }
""".lstrip()

    out = tmp_path / "a.out"
    p = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "pycc.py"),
            "-",
           
            "-o",
            str(out),
        ],
        cwd=str(tmp_path),
        input=src_text,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert p.returncode == 0, (p.stdout, p.stderr)
    assert out.exists()

    r = subprocess.run(
        [str(out)],
        cwd=str(tmp_path),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert r.returncode == 0, (r.stdout, r.stderr)
    assert r.stdout == "hi\n"
