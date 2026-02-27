import subprocess
import sys
from pathlib import Path


def _run_E(args, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def test_include_guard_header_included_twice_emits_once(tmp_path: Path):
    inc = tmp_path / "inc"
    inc.mkdir()
    (inc / "h.h").write_text(
        (
            "#ifndef H_H\n"
            "#define H_H 1\n"
            "int guarded = 123;\n"
            "#endif\n"
        )
    )

    src = tmp_path / "main.c"
    src.write_text('#include "h.h"\n#include "h.h"\nint x = guarded;\n')

    res = _run_E(
        [sys.executable, "pycc.py", "-E", str(src), "-I", str(inc)],
        cwd=Path(__file__).resolve().parents[1],
    )
    assert res.returncode == 0, res.stderr
    assert res.stdout.count("int guarded = 123;") == 1


def test_pragma_once_header_included_twice_emits_once(tmp_path: Path):
    inc = tmp_path / "inc"
    inc.mkdir()
    (inc / "po.h").write_text("#pragma once\nint once = 7;\n")

    src = tmp_path / "main.c"
    src.write_text('#include "po.h"\n#include "po.h"\nint x = once;\n')

    res = _run_E(
        [sys.executable, "pycc.py", "-E", str(src), "-I", str(inc)],
        cwd=Path(__file__).resolve().parents[1],
    )
    assert res.returncode == 0, res.stderr
    assert res.stdout.count("int once = 7;") == 1
