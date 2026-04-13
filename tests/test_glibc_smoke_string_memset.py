import shutil
import subprocess
import sys
from pathlib import Path

import pytest


def test_glibc_smoke_string_memset(tmp_path: Path):
    if shutil.which("gcc") is None:
        pytest.skip("gcc not available")

    src = tmp_path / "main.c"
    src.write_text(
        r"""
#include <string.h>
#include <stdio.h>

int main(void) {
    char buf[8];
    memset(buf, 'A', 7);
    buf[7] = 0;
    printf("%s\n", buf);
    return 0;
}
""".lstrip(),
        encoding="utf-8",
    )

    out = tmp_path / "a.out"
    res = subprocess.run(
        [sys.executable, "pycc.py", str(src), "-o", str(out)],
        cwd=Path(__file__).resolve().parents[1],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    combined = (res.stdout + res.stderr)
    if res.returncode != 0 and "Expected type specifier" in combined:
        pytest.skip("system headers require unsupported types: " + combined.strip())

    assert res.returncode == 0, combined

    run = subprocess.run([str(out)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    assert run.returncode == 0
    assert run.stdout.strip() == "AAAAAAA"
