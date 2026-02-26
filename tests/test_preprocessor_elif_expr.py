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


def test_E_elif_defined_in_expr(tmp_path: Path):
    res = _run_E(
        tmp_path,
        r"""
#define X 1
#if 0
int x = 0;
#elif defined(X)
int x = 1;
#else
int x = 2;
#endif
""".lstrip(),
    )
    assert res.returncode == 0, res.stderr
    assert "int x = 1;" in res.stdout
    assert "int x = 0;" not in res.stdout
    assert "int x = 2;" not in res.stdout


def test_E_elif_arith_expr(tmp_path: Path):
    res = _run_E(
        tmp_path,
        r"""
#define X 1
#if 0
int x = 0;
#elif X + 1 == 2
int x = 1;
#else
int x = 2;
#endif
""".lstrip(),
    )
    assert res.returncode == 0, res.stderr
    assert "int x = 1;" in res.stdout
    assert "int x = 0;" not in res.stdout
    assert "int x = 2;" not in res.stdout


def test_E_elif_expr_respects_taken_branch(tmp_path: Path):
    res = _run_E(
        tmp_path,
        r"""
#define X 1
#if 1
int x = 0;
#elif X + 1 == 2
int x = 1;
#else
int x = 2;
#endif
""".lstrip(),
    )
    assert res.returncode == 0, res.stderr
    assert "int x = 0;" in res.stdout
    assert "int x = 1;" not in res.stdout
    assert "int x = 2;" not in res.stdout
