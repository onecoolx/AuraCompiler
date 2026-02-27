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


def test_E___STDC___expands_to_1(tmp_path: Path):
    res = _run_E(tmp_path, "int a = __STDC__;\n")
    assert res.returncode == 0, res.stderr
    assert "int a = 1;" in res.stdout


def test_E___DATE___and___TIME___are_string_literals(tmp_path: Path):
    res = _run_E(tmp_path, "const char *d = __DATE__; const char *t = __TIME__;\n")
    assert res.returncode == 0, res.stderr
    # Subset: accept that they are emitted as C string literals
    assert 'const char *d = "' in res.stdout
    assert 'const char *t = "' in res.stdout
