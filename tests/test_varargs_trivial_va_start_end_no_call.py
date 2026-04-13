import shutil
import subprocess
import sys
from pathlib import Path

import pytest


def test_varargs_trivial_va_start_end_no_call(tmp_path: Path):
    if shutil.which("gcc") is None:
        pytest.skip("gcc not available")

    src = tmp_path / "main.c"
    src.write_text(
        r"""
#include <stdarg.h>

static int f(int x, ...) {
    va_list ap;
    va_start(ap, x);
    va_end(ap);
    return x;
}

int main(void) {
    return f(0) == 0 ? 0 : 1;
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
    assert res.returncode == 0, combined

    run = subprocess.run([str(out)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    assert run.returncode == 0
