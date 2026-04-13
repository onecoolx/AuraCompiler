import shutil
import subprocess
import sys
from pathlib import Path


def test_varargs_va_list_pass_to_libc_vsnprintf(tmp_path: Path):
    """Minimal milestone: passing a va_list to libc vsnprintf must work.

    This is a narrower repro than the glibc smoke and should become green
    once we implement __builtin_va_start/__builtin_va_end lowering + ABI.
    """

    if shutil.which("gcc") is None:
        return

    src = tmp_path / "main.c"
    src.write_text(
        r"""
#include <stdarg.h>
#include <stdio.h>

static int wrap(char* out, int n, const char* fmt, ...) {
    va_list ap;
    __builtin_va_start(ap, fmt);
    int rc = vsnprintf(out, n, fmt, ap);
    __builtin_va_end(ap);
    return rc;
}

int main(void) {
    char buf[64];
    int n = wrap(buf, 64, "%s %d", "hi", 7);
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
    assert res.returncode == 0, (res.stdout + res.stderr)

    run = subprocess.run([str(out)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert run.returncode == 0
