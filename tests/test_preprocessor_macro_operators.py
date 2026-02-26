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


def test_E_stringize_hash_operator(tmp_path: Path):
    res = _run_E(
        tmp_path,
        r"""
#define STR(x) #x
const char *s = STR(hello);
""".lstrip(),
    )
    assert res.returncode == 0, res.stderr
    assert 'const char *s = "hello";' in res.stdout


def test_E_token_paste_operator(tmp_path: Path):
    res = _run_E(
        tmp_path,
        r"""
#define CAT(a,b) a##b
int xy = 3;
int main(){
  return CAT(x, y);
}
""".lstrip(),
    )
    assert res.returncode == 0, res.stderr
    assert "return xy;" in res.stdout
