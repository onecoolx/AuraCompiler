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


def test_E_error_directive_ignored_in_inactive_region(tmp_path: Path):
    res = _run_E(
        tmp_path,
        r"""
#if 0
#error should_not_fire
#endif
int ok;
""".lstrip(),
    )
    assert res.returncode == 0, res.stderr
    assert "int ok;" in res.stdout
