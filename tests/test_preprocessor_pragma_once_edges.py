import subprocess
import sys
from pathlib import Path


def _run_E(args, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def test_pragma_once_in_skipped_region_does_not_activate(tmp_path: Path):
    inc = tmp_path / "inc"
    inc.mkdir()
    (inc / "po.h").write_text(
        (
            "#if 0\n"
            "#pragma once\n"
            "#endif\n"
            "int once = 7;\n"
        )
    )

    src = tmp_path / "main.c"
    src.write_text('#include "po.h"\n#include "po.h"\n')

    res = _run_E(
        [sys.executable, "pycc.py", "-E", str(src), "-I", str(inc)],
        cwd=Path(__file__).resolve().parents[1],
    )
    assert res.returncode == 0, res.stderr
    # pragma once is skipped, so header is included twice
    assert res.stdout.count("int once = 7;") == 2


def test_pragma_once_late_activation_skips_second_include(tmp_path: Path):
    inc = tmp_path / "inc"
    inc.mkdir()
    (inc / "po.h").write_text(
        (
            "int a = 1;\n"
            "#pragma once\n"
            "int b = 2;\n"
        )
    )

    src = tmp_path / "main.c"
    src.write_text('#include "po.h"\n#include "po.h"\n')

    res = _run_E(
        [sys.executable, "pycc.py", "-E", str(src), "-I", str(inc)],
        cwd=Path(__file__).resolve().parents[1],
    )
    assert res.returncode == 0, res.stderr
    # First include emits both lines; second include should be skipped entirely.
    assert res.stdout.count("int a = 1;") == 1
    assert res.stdout.count("int b = 2;") == 1
