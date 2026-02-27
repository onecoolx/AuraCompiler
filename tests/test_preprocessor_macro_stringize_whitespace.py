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


def test_E_stringize_normalizes_internal_whitespace_to_single_spaces(tmp_path: Path):
    res = _run_E(
        tmp_path,
        (
            "#define STR(x) #x\n"
            "const char *s = STR(  a\t   +\t\t b   );\n"
        ),
    )
    assert res.returncode == 0, res.stderr
    assert 'const char *s = "a + b";' in res.stdout
