import subprocess
import sys
from pathlib import Path


def _run_E(tmp_path: Path, *, src_text: str, args) -> subprocess.CompletedProcess:
    src = tmp_path / "main.c"
    src.write_text(src_text)
    return subprocess.run(
        [sys.executable, "pycc.py", *args, "-E", str(src)],
        cwd=Path(__file__).resolve().parents[1],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def test_E_I_angle_include_searches_I_dirs_only(tmp_path: Path):
    inc = tmp_path / "inc"
    inc.mkdir()
    (inc / "a.h").write_text("int A = 1;\n")

    res = _run_E(
        tmp_path,
        src_text='#include <a.h>\n',
        args=["-I", str(inc)],
    )
    assert res.returncode == 0, res.stderr
    assert "int A = 1;" in res.stdout


def test_E_I_quote_include_prefers_local_dir_then_I_dirs(tmp_path: Path):
    # local a.h in same dir as main.c
    (tmp_path / "a.h").write_text("int A = 2;\n")

    inc = tmp_path / "inc"
    inc.mkdir()
    (inc / "a.h").write_text("int A = 1;\n")

    res = _run_E(
        tmp_path,
        src_text='#include "a.h"\n',
        args=["-I", str(inc)],
    )
    assert res.returncode == 0, res.stderr
    assert "int A = 2;" in res.stdout
    assert "int A = 1;" not in res.stdout


def test_E_I_quote_include_uses_I_dirs_when_not_local(tmp_path: Path):
    inc = tmp_path / "inc"
    inc.mkdir()
    (inc / "a.h").write_text("int A = 1;\n")

    res = _run_E(
        tmp_path,
        src_text='#include "a.h"\n',
        args=["-I", str(inc)],
    )
    assert res.returncode == 0, res.stderr
    assert "int A = 1;" in res.stdout
