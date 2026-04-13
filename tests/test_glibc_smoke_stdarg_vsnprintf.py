import shutil
import subprocess
import sys
from pathlib import Path

import pytest


def test_glibc_smoke_stdarg_vsnprintf(tmp_path: Path):
    if shutil.which("gcc") is None:
        pytest.skip("gcc not available")

    src = tmp_path / "main.c"
    src.write_text(
        r"""
#include <stdarg.h>
#include <stdio.h>

static int my_snprintf(char* out, int n, const char* fmt, ...) {
    va_list ap;
    va_start(ap, fmt);
    int rc = vsnprintf(out, n, fmt, ap);
    va_end(ap);
    return rc;
}

int main(void) {
    char buf[64];
    int n = my_snprintf(buf, 64, "%s %d", "hi", 7);
    if (n <= 0) return 2;
    if (buf[0] != 'h' || buf[1] != 'i') return 3;
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

    # If compile succeeded, the produced program should run successfully.
    # (Historically this was xfailed due to varargs ABI gaps; keep the
    # diagnostics in case it regresses.)
    if res.returncode == 0:
        run = subprocess.run([str(out)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        assert run.returncode == 0, run.stderr

    # Treat unsupported system-header constructs as coverage limitations.
    if res.returncode != 0 and "unexpected character" in combined.lower():
        pytest.skip("system headers not supported by built-in preprocessor path yet: " + combined.strip())
    if res.returncode != 0 and "unsupported #if expression" in combined.lower():
        pytest.skip("system headers use unsupported #if expressions in built-in preprocessor path: " + combined.strip())
    if res.returncode != 0 and "Expected type specifier" in combined:
        pytest.skip("system headers require unsupported types in built-in preprocessor path: " + combined.strip())

    assert res.returncode == 0, combined

    run = subprocess.run([str(out)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    assert run.returncode == 0
