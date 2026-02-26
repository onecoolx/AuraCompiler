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


def test_E_object_like_macro_rescans_to_fixed_point(tmp_path: Path):
    res = _run_E(
        tmp_path,
        r"""
#define B 1
#define A B
int main(){ return A; }
""".lstrip(),
    )
    assert res.returncode == 0, res.stderr
    assert "return 1;" in res.stdout


def test_E_object_like_macro_self_reference_does_not_loop(tmp_path: Path):
    res = _run_E(
        tmp_path,
        r"""
#define A A
int main(){ return A; }
""".lstrip(),
    )
    assert res.returncode == 0, res.stderr
    # Best-effort: must not hang; leave it unchanged.
    assert "return A;" in res.stdout
