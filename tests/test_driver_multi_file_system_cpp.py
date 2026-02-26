import shutil
import subprocess
import sys
from pathlib import Path

import pytest


def test_driver_multiple_inputs_with_system_cpp(tmp_path: Path):
    if shutil.which("gcc") is None:
        pytest.skip("gcc not available")

    a = tmp_path / "a.c"
    b = tmp_path / "b.c"
    out = tmp_path / "a.out"

    a.write_text(
        r"""
#include <stdio.h>
extern int get(void);

int main(void) {
  printf("%d\n", get());
  return 0;
}
""".lstrip()
    )

    b.write_text(
        r"""
int get(void) {
  return 42;
}
""".lstrip()
    )

    repo_root = Path(__file__).resolve().parents[1]
    p = subprocess.run(
        [
            sys.executable,
            "pycc.py",
            "--use-system-cpp",
            str(a),
            str(b),
            "-o",
            str(out),
        ],
        cwd=repo_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert p.returncode == 0, p.stdout + p.stderr

    run = subprocess.run([str(out)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    assert run.returncode == 0
    assert run.stdout.strip() == "42"
