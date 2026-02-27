import subprocess
import sys
from pathlib import Path


def _run_E(args, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def test_include_cycle_broken_by_pragma_once(tmp_path: Path):
    inc = tmp_path / "inc"
    inc.mkdir()

    # a.h includes b.h; b.h includes a.h, but both have pragma once.
    (inc / "a.h").write_text('#pragma once\n#include "b.h"\nint a = 1;\n')
    (inc / "b.h").write_text('#pragma once\n#include "a.h"\nint b = 2;\n')

    src = tmp_path / "main.c"
    src.write_text('#include "a.h"\n')

    res = _run_E(
        [sys.executable, "pycc.py", "-E", str(src), "-I", str(inc)],
        cwd=Path(__file__).resolve().parents[1],
    )
    assert res.returncode == 0, res.stderr
    out = res.stdout
    assert "int a = 1;" in out
    assert "int b = 2;" in out
