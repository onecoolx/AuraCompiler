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


def test_E_function_like_macro_expands_arguments(tmp_path: Path):
    res = _run_E(
        tmp_path,
        r"""
#define B 1
#define INC(x) ((x)+1)
int main(){ return INC(B); }
""".lstrip(),
    )
    assert res.returncode == 0, res.stderr
    assert "return ((1)+1);" in res.stdout
