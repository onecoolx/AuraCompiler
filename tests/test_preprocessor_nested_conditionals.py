import subprocess
import sys
from pathlib import Path


def _run_E(tmp_path: Path, text: str) -> subprocess.CompletedProcess:
    c_path = tmp_path / "t.c"
    c_path.write_text(text)
    return subprocess.run(
        [sys.executable, "pycc.py", "-E", str(c_path)],
        cwd=Path(__file__).resolve().parents[1],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def test_E_nested_if_else_in_active_region(tmp_path: Path):
    res = _run_E(
        tmp_path,
        r"""
#define OUTER 1
#if OUTER
  #if 0
  int x = 0;
  #else
  int x = 1;
  #endif
#else
int x = 2;
#endif
""".lstrip(),
    )
    assert res.returncode == 0, res.stderr
    assert "int x = 1;" in res.stdout
    assert "int x = 0;" not in res.stdout
    assert "int x = 2;" not in res.stdout


def test_E_nested_conditionals_in_skipped_region_do_not_leak(tmp_path: Path):
    res = _run_E(
        tmp_path,
        r"""
#define OUTER 0
#if OUTER
  #if 1
  int x = 0;
  #else
  int x = 1;
  #endif
#else
int x = 2;
#endif
""".lstrip(),
    )
    assert res.returncode == 0, res.stderr
    assert "int x = 2;" in res.stdout
    assert "int x = 0;" not in res.stdout
    assert "int x = 1;" not in res.stdout


def test_E_nested_ifdef_inside_ifndef(tmp_path: Path):
    res = _run_E(
        tmp_path,
        r"""
#ifndef A
  #define B 1
  #ifdef B
  int x = 3;
  #else
  int x = 4;
  #endif
#else
int x = 5;
#endif
""".lstrip(),
    )
    assert res.returncode == 0, res.stderr
    assert "int x = 3;" in res.stdout
    assert "int x = 4;" not in res.stdout
    assert "int x = 5;" not in res.stdout
