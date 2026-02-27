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


def test_E_define_in_inactive_region_has_no_effect(tmp_path: Path):
    res = _run_E(
        tmp_path,
        r"""
#if 0
#define A 1
#endif
int main(){ return A; }
""".lstrip(),
    )
    assert res.returncode == 0, res.stderr
    # Define in inactive region should not take effect.
    assert "return A;" in res.stdout
    assert "return 1;" not in res.stdout
