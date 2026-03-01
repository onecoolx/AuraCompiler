import shutil
import subprocess
import sys
from pathlib import Path

import pytest


def test_glibc_smoke_string_memcmp(tmp_path: Path):
    if shutil.which("gcc") is None:
        pytest.skip("gcc not available")

    src = tmp_path / "main.c"
    src.write_text(
        r"""
#include <string.h>
#include <stdio.h>

int main(void) {
    char a[4];
    char b[4];
    memcpy(a, "abc", 4);
    memcpy(b, "abd", 4);

    int r1 = memcmp(a, a, 4);
    int r2 = memcmp(a, b, 4);

    /* Only require sign, not exact value. */
    printf("%d %d\n", r1 == 0, r2 < 0);
    return 0;
}
""".lstrip(),
        encoding="utf-8",
    )

    out = tmp_path / "a.out"
    res = subprocess.run(
        [sys.executable, "pycc.py", "--use-system-cpp", str(src), "-o", str(out)],
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
    assert run.stdout.strip() == "1 1"
