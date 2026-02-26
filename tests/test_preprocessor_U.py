import subprocess
import sys
from pathlib import Path


def _run_E(tmp_path: Path, text: str, args) -> subprocess.CompletedProcess:
    c_path = tmp_path / "t.c"
    c_path.write_text(text)
    return subprocess.run(
        [sys.executable, "pycc.py", *args, "-E", str(c_path)],
        cwd=Path(__file__).resolve().parents[1],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def test_E_U_removes_macro_defined_by_D(tmp_path: Path):
    res = _run_E(
        tmp_path,
        r"""
#if DEBUG
int x = 1;
#else
int x = 2;
#endif
""".lstrip(),
        args=["-DDEBUG=1", "-UDEBUG"],
    )
    assert res.returncode == 0, res.stderr
    assert "int x = 1;" not in res.stdout
    assert "int x = 2;" in res.stdout


def test_E_U_on_unknown_macro_is_ok(tmp_path: Path):
    res = _run_E(
        tmp_path,
        r"""
#if DEBUG
int x = 1;
#else
int x = 2;
#endif
""".lstrip(),
        args=["-UDEBUG"],
    )
    assert res.returncode == 0, res.stderr
    assert "int x = 1;" not in res.stdout
    assert "int x = 2;" in res.stdout
