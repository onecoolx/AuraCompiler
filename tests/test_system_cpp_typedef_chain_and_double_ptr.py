import shutil
import subprocess
import sys
from pathlib import Path

import pytest


def test_system_cpp_typedef_chain_and_double_ptr(tmp_path: Path):
    """Regression: system-preprocessed headers contain typedef chains and T** prototypes.

    This is a minimal reproduction of patterns seen in glibc headers like <ctype.h>:
      - typedef __int32_t int32_t;
      - extern const __int32_t **foo(void);

    We don't need to call foo; we just need to parse the prototype.
    """

    if shutil.which("gcc") is None:
        pytest.skip("gcc not available")

    src = tmp_path / "main.c"
    src.write_text(
        r"""
typedef int __int32_t;
extern const __int32_t **foo(void);

int main(void) {
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
    assert res.returncode == 0, combined
