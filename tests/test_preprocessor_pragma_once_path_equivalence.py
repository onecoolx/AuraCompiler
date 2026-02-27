import subprocess
import sys
from pathlib import Path


def _run_E(args, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def test_pragma_once_same_file_different_include_spellings(tmp_path: Path):
    inc = tmp_path / "inc"
    (inc / "dir").mkdir(parents=True)
    header = inc / "dir" / "po.h"
    header.write_text("#pragma once\nint once = 42;\n")

    src = tmp_path / "main.c"
    # Include same file via a relative path from -I root, and via -I dir basename.
    src.write_text(
        (
            '#include "dir/po.h"\n'
            '#include "po.h"\n'
            "int x = once;\n"
        )
    )

    res = _run_E(
        [
            sys.executable,
            "pycc.py",
            "-E",
            str(src),
            "-I",
            str(inc),
            "-I",
            str(inc / "dir"),
        ],
        cwd=Path(__file__).resolve().parents[1],
    )
    assert res.returncode == 0, res.stderr
    assert res.stdout.count("int once = 42;") == 1
