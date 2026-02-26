import subprocess
from pathlib import Path


def test_preprocessor_E_if0_strips_block(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]

    src = tmp_path / "t.c"
    src.write_text(
        """
#if 0
int bad = does_not_parse(;
#endif
int main(){ return 0; }
""".lstrip()
    )

    p = subprocess.run(
        ["python", "pycc.py", "-E", str(src)],
        cwd=str(repo_root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert p.returncode == 0, p.stdout + p.stderr

    out = p.stdout
    assert "does_not_parse" not in out
    assert "int main" in out
