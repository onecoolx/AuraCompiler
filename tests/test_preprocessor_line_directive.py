import subprocess
import sys
from pathlib import Path


def test_preprocessor_E_line_directive_is_stripped(tmp_path: Path):
    repo_root = Path(__file__).resolve().parents[1]

    src = tmp_path / "t.c"
    src.write_text(
        r"""
#line 123 "fake.c"
int x = 1;
""".lstrip()
    )

    p = subprocess.run(
        [sys.executable, "pycc.py", "-E", str(src)],
        cwd=str(repo_root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert p.returncode == 0, p.stdout + p.stderr
    out = p.stdout
    assert "#line" not in out
    assert "int x = 1;" in out
