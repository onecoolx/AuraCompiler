import subprocess
from pathlib import Path


def test_preprocessor_E_if0_else_keeps_else_branch(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]

    src = tmp_path / "t.c"
    src.write_text(
        """
#if 0
int x = 1;
#else
int x = 2;
#endif
int main(){ return x; }
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
    assert "int x = 1;" not in out
    assert "int x = 2;" in out


def test_preprocessor_E_if1_else_keeps_if_branch(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]

    src = tmp_path / "t.c"
    src.write_text(
        """
#if 1
int x = 3;
#else
int x = 4;
#endif
int main(){ return x; }
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
    assert "int x = 3;" in out
    assert "int x = 4;" not in out
