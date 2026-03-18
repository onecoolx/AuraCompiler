import subprocess
import sys
from pathlib import Path


def _run_E(tmp_path: Path, text: str) -> subprocess.CompletedProcess:
    repo_root = Path(__file__).resolve().parents[1]
    c_path = tmp_path / "t.c"
    c_path.write_text(text)
    return subprocess.run(
        [sys.executable, "pycc.py", "-E", str(c_path)],
        cwd=str(repo_root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def test_E_line_directive_updates___LINE___and___FILE__(tmp_path: Path):
    res = _run_E(
        tmp_path,
        (
            '#line 123 "fake.c"\n'
            "int a = __LINE__;\n"
            "const char *p = __FILE__;\n"
        ),
    )
    assert res.returncode == 0, res.stdout + res.stderr
    out = res.stdout
    assert "#line" not in out
    assert "int a = 123;" in out
    assert 'const char *p = "fake.c";' in out
