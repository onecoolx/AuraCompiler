from __future__ import annotations

import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_driver_dump_preprocessed_writes_i(tmp_path):
    inc = tmp_path / "inc"
    inc.mkdir()
    (inc / "h.h").write_text("#define X 123\n", encoding="utf-8")

    c_path = tmp_path / "t.c"
    c_path.write_text(
        """
#include "h.h"
int main(void){ return X; }
""".lstrip(),
        encoding="utf-8",
    )

    r = subprocess.run(
        [
            "python",
            str(REPO_ROOT / "pycc.py"),
            str(c_path),
            "-I",
            str(inc),
            "--dump-preprocessed",
            "-o",
            str(tmp_path / "a.out"),
        ],
        cwd=str(tmp_path),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert r.returncode == 0, (r.stdout, r.stderr)
    out_i = tmp_path / "pycc-tmp.i"
    assert out_i.exists()
    txt = out_i.read_text(encoding="utf-8")
    assert "123" in txt
