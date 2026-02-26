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


def test_E_if_expr_arithmetic_eq(tmp_path: Path):
    res = _run_E(
        tmp_path,
        r"""
#if 1 + 2 == 3
int x = 1;
#else
int x = 2;
#endif
""".lstrip(),
    )
    assert res.returncode == 0, res.stderr
    assert "int x = 1;" in res.stdout
    assert "int x = 2;" not in res.stdout


def test_E_if_expr_logical_ops(tmp_path: Path):
    res = _run_E(
        tmp_path,
        r"""
#if 0 || 1
int x = 1;
#else
int x = 2;
#endif

#if 0 && 1
int y = 1;
#else
int y = 2;
#endif
""".lstrip(),
    )
    assert res.returncode == 0, res.stderr
    assert "int x = 1;" in res.stdout
    assert "int y = 2;" in res.stdout


def test_E_if_expr_not(tmp_path: Path):
    res = _run_E(
        tmp_path,
        r"""
#if !0
int x = 1;
#else
int x = 2;
#endif

#if !1
int y = 1;
#else
int y = 2;
#endif
""".lstrip(),
    )
    assert res.returncode == 0, res.stderr
    assert "int x = 1;" in res.stdout
    assert "int y = 2;" in res.stdout


def test_E_if_expr_defined_and_numeric_macro(tmp_path: Path):
    res = _run_E(
        tmp_path,
        r"""
#define X 1
#if defined(X) && (X == 1)
int x = 1;
#else
int x = 2;
#endif
""".lstrip(),
    )
    assert res.returncode == 0, res.stderr
    assert "int x = 1;" in res.stdout
    assert "int x = 2;" not in res.stdout
