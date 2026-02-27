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


def test_E_defined_does_not_expand_macro_argument(tmp_path: Path):
    res = _run_E(
        tmp_path,
        r"""
#define NAME A
#define A 1
#if defined(NAME)
int ok;
#else
int bad;
#endif
""".lstrip(),
    )
    assert res.returncode == 0, res.stderr
    # In C, defined(NAME) tests whether NAME is defined, without macro-expanding NAME.
    assert "int ok;" in res.stdout
    assert "int bad;" not in res.stdout
