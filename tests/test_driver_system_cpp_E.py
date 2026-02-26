import shutil
import subprocess
import sys
from pathlib import Path

import pytest


def test_driver_use_system_cpp_E_writes_output(tmp_path: Path):
    if shutil.which("gcc") is None:
        pytest.skip("gcc not available")

    src = tmp_path / "t.c"
    src.write_text(
        r"""
#include <stdio.h>
int main(void){ return 0; }
""".lstrip()
    )

    out = tmp_path / "out.i"
    p = subprocess.run(
        [sys.executable, "pycc.py", "--use-system-cpp", "-E", str(src), "-o", str(out)],
        cwd=Path(__file__).resolve().parents[1],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert p.returncode == 0, p.stdout + p.stderr
    text = out.read_text()
    # A weak but stable assertion that preprocessing worked and included stdio.
    assert "extern" in text
    assert "printf" in text
