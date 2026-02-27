import os
import subprocess
import sys
from pathlib import Path


def _run_E(args, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def test_pragma_once_symlink_and_realpath_same_file(tmp_path: Path):
    inc = tmp_path / "inc"
    (inc / "real").mkdir(parents=True)
    (inc / "link").mkdir(parents=True)

    real_hdr = inc / "real" / "po.h"
    real_hdr.write_text("#pragma once\nint once = 9;\n")

    link_hdr = inc / "link" / "po.h"
    os.symlink(real_hdr, link_hdr)

    src = tmp_path / "main.c"
    src.write_text('#include "po.h"\n#include "po.h"\n')

    # First include resolves via -I link, second via -I real (same include spelling).
    res = _run_E(
        [
            sys.executable,
            "pycc.py",
            "-E",
            str(src),
            "-I",
            str(inc / "link"),
            "-I",
            str(inc / "real"),
        ],
        cwd=Path(__file__).resolve().parents[1],
    )
    assert res.returncode == 0, res.stderr
    assert res.stdout.count("int once = 9;") == 1
