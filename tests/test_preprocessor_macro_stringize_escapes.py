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


def test_E_stringize_escapes_backslash_and_quote(tmp_path: Path):
    res = _run_E(
        tmp_path,
        r"""
#define STR(x) #x
const char *s1 = STR(a\b);
const char *s2 = STR(a"b);
""".lstrip(),
    )
    assert res.returncode == 0, res.stderr
    # C stringization escapes backslashes and double-quotes.
    assert 'const char *s1 = "a\\\\b";' in res.stdout
    assert 'const char *s2 = "a\\\"b";' in res.stdout
