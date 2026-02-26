import subprocess
from pathlib import Path


def test_preprocessor_E_elif_selects_first_true_branch(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]

    src = tmp_path / "t.c"
    src.write_text(
        """
#if 0
int x = 1;
#elif 1
int x = 2;
#else
int x = 3;
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
    assert "int x = 3;" not in out


def test_preprocessor_E_elif_all_false_falls_to_else(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]

    src = tmp_path / "t.c"
    src.write_text(
        """
#if 0
int x = 10;
#elif 0
int x = 20;
#else
int x = 30;
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
    assert "int x = 10;" not in out
    assert "int x = 20;" not in out
    assert "int x = 30;" in out
