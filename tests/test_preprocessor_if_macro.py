import subprocess
import sys
from pathlib import Path

import pytest


def _run_E(tmp_path: Path, text: str, *, expect_ok: bool = True) -> subprocess.CompletedProcess:
    c_path = tmp_path / "t.c"
    c_path.write_text(text)
    res = subprocess.run(
        [sys.executable, "pycc.py", "-E", str(c_path)],
        cwd=Path(__file__).resolve().parents[1],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if expect_ok:
        assert res.returncode == 0, res.stderr
    else:
        assert res.returncode != 0
    return res


def test_E_if_macro_name_expands_to_1(tmp_path: Path):
    res = _run_E(
        tmp_path,
        r"""
#define FOO 1
#if FOO
int x = 1;
#else
int x = 2;
#endif
""".lstrip(),
    )
    assert "int x = 1;" in res.stdout
    assert "int x = 2;" not in res.stdout


def test_E_if_macro_name_expands_to_0(tmp_path: Path):
    res = _run_E(
        tmp_path,
        r"""
#define FOO 0
#if FOO
int x = 1;
#else
int x = 2;
#endif
""".lstrip(),
    )
    assert "int x = 1;" not in res.stdout
    assert "int x = 2;" in res.stdout


def test_E_if_undefined_name_is_false(tmp_path: Path):
    res = _run_E(
        tmp_path,
        r"""
#if FOO
int x = 1;
#else
int x = 2;
#endif
""".lstrip(),
    )
    assert "int x = 1;" not in res.stdout
    assert "int x = 2;" in res.stdout


def test_E_elif_macro_name_expands_to_1(tmp_path: Path):
    res = _run_E(
        tmp_path,
        r"""
#define A 0
#define B 1
#if A
int x = 1;
#elif B
int x = 2;
#else
int x = 3;
#endif
""".lstrip(),
    )
    assert "int x = 1;" not in res.stdout
    assert "int x = 2;" in res.stdout
    assert "int x = 3;" not in res.stdout


def test_E_if_macro_name_expands_to_non_01_is_rejected(tmp_path: Path):
    res = _run_E(
        tmp_path,
        r"""
#define FOO 2
#if FOO
int x = 1;
#endif
""".lstrip(),
        expect_ok=False,
    )
    assert "unsupported" in (res.stderr + res.stdout).lower()
