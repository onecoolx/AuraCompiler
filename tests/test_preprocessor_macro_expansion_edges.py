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


def test_E_macro_not_expanded_in_string_or_char_literals(tmp_path: Path):
    res = _run_E(
        tmp_path,
        r"""
#define N 7
const char *s = "N";
int c = 'N';
int main(){ return N; }
""".lstrip(),
    )
    assert res.returncode == 0, res.stderr
    assert 'const char *s = "N";' in res.stdout
    assert "int c = 'N';" in res.stdout
    assert "return 7;" in res.stdout


def test_E_macro_replaces_only_identifier_token(tmp_path: Path):
    res = _run_E(
        tmp_path,
        r"""
#define A 1
int AB = 2;
int main(){ return A + AB; }
""".lstrip(),
    )
    assert res.returncode == 0, res.stderr
    assert "int AB = 2;" in res.stdout
    assert "return 1 + AB;" in res.stdout
