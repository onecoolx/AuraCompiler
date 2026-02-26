import subprocess
import sys
from pathlib import Path

import pytest


def _run_E(tmp_path: Path, text: str) -> str:
    c_path = tmp_path / "t.c"
    c_path.write_text(text)
    res = subprocess.run(
        [sys.executable, "pycc.py", "-E", str(c_path)],
        cwd=Path(__file__).resolve().parents[1],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert res.returncode == 0, res.stderr
    return res.stdout


def test_E_ifdef_true_branch(tmp_path: Path):
    out = _run_E(
        tmp_path,
        r"""
#define N 1
#ifdef N
int x = 2;
#else
int x = 3;
#endif
int main() { return x; }
""".lstrip(),
    )
    assert "int x = 2;" in out
    assert "int x = 3;" not in out


def test_E_ifdef_false_branch(tmp_path: Path):
    out = _run_E(
        tmp_path,
        r"""
#ifdef N
int x = 2;
#else
int x = 3;
#endif
""".lstrip(),
    )
    assert "int x = 2;" not in out
    assert "int x = 3;" in out


def test_E_ifndef_with_undef(tmp_path: Path):
    out = _run_E(
        tmp_path,
        r"""
#define N 1
#undef N
#ifndef N
int x = 7;
#else
int x = 8;
#endif
""".lstrip(),
    )
    assert "int x = 7;" in out
    assert "int x = 8;" not in out


def test_E_ifdef_macro_defined_in_skipped_region_does_not_count(tmp_path: Path):
    out = _run_E(
        tmp_path,
        r"""
#if 0
#define N 1
#endif
#ifdef N
int x = 1;
#else
int x = 2;
#endif
""".lstrip(),
    )
    assert "int x = 1;" not in out
    assert "int x = 2;" in out
