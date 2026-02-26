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


def test_E_error_directive_fails_when_active(tmp_path: Path):
    res = _run_E(
        tmp_path,
        r"""
#error boom
int x = 1;
""".lstrip(),
    )
    assert res.returncode != 0
    msg = (res.stdout + res.stderr).lower()
    assert "boom" in msg


def test_E_error_directive_ignored_in_skipped_region(tmp_path: Path):
    res = _run_E(
        tmp_path,
        r"""
#if 0
#error should_not_trigger
#endif
int x = 1;
""".lstrip(),
    )
    assert res.returncode == 0, res.stderr
    assert "int x = 1;" in res.stdout
