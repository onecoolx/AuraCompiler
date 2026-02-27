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


def test_E_token_paste_does_not_expand_arguments_before_paste(tmp_path: Path):
    res = _run_E(
        tmp_path,
        r"""
#define A x
#define B y
#define xA A
#define yB B
#define AB xy
#define CAT(a,b) a##b
int xy = 9;
int main(){ return CAT(A, B); }
""".lstrip(),
    )
    assert res.returncode == 0, res.stderr
    # C rule: macro arguments are not macro-expanded before token pasting.
    # Here, pasting should form `AB`, then rescanning expands `AB` -> `xy`.
    assert "return xy;" in res.stdout
    assert "return AB;" not in res.stdout
