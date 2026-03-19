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


def test_E_variadic_macro_basic_substitution(tmp_path: Path):
    res = _run_E(
        tmp_path,
        r"""
#define V(fmt, ...) fmt, __VA_ARGS__
int x = V(1, 2, 3);
""".lstrip(),
    )
    assert res.returncode == 0, res.stderr
    assert "int x = 1, 2, 3;" in res.stdout


def test_E_variadic_macro_empty_va_args_is_allowed(tmp_path: Path):
    res = _run_E(
        tmp_path,
        r"""
#define V(fmt, ...) fmt __VA_ARGS__
int x = V(1);
""".lstrip(),
    )
    assert res.returncode == 0, res.stderr
    # Subset expectation: empty __VA_ARGS__ disappears (may leave extra whitespace).
    assert "int x = 1" in res.stdout
