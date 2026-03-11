from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_driver_E_stdin_dash_use_system_cpp(tmp_path: Path):
    if shutil.which("gcc") is None:
        pytest.skip("gcc not available")

    src_text = """
#include <stddef.h>
int x = (int)sizeof(size_t);
""".lstrip()

    r = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "pycc.py"),
            "--use-system-cpp",
            "-E",
            "-",
        ],
        cwd=str(tmp_path),
        input=src_text,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    assert r.returncode == 0, (r.stdout, r.stderr)
    # Weak but stable signal that system headers were expanded.
    assert "typedef" in r.stdout
