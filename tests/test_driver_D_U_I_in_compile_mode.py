from __future__ import annotations

import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_driver_D_U_I_flags_work_in_compile_mode(tmp_path):
    inc = tmp_path / "inc"
    inc.mkdir()

    (inc / "h.h").write_text(
        """
#define X 7
""".lstrip(),
        encoding="utf-8",
    )

    c_path = tmp_path / "t.c"
    c_path.write_text(
        """
#include "h.h"

#ifndef X
#error missing X
#endif

int main(void) {
  return X == 7 ? 0 : 1;
}
""".lstrip(),
        encoding="utf-8",
    )

    out = tmp_path / "a.out"
    r = subprocess.run(
        [
            "python",
            str(REPO_ROOT / "pycc.py"),
            str(c_path),
            "-I",
            str(inc),
            "-D",
            "X=8",
            "-U",
            "X",
            "-D",
            "X=7",
            "-o",
            str(out),
        ],
        cwd=str(tmp_path),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert r.returncode == 0, (r.stdout, r.stderr)
    rr = subprocess.run([str(out)])
    assert rr.returncode == 0
