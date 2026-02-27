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


def test_E_if_expr_undefined_identifier_is_0(tmp_path: Path):
    res = _run_E(
        tmp_path,
        r"""
#if UNDEF + 1 == 1
int ok;
#else
int bad;
#endif
""".lstrip(),
    )
    assert res.returncode == 0, res.stderr
    # In C, undefined identifiers in #if expressions evaluate to 0.
    assert "int ok;" in res.stdout
    assert "int bad;" not in res.stdout
