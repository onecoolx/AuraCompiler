import subprocess
from pathlib import Path


def test_preprocessor_E_undef_removes_macro(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]

    src = tmp_path / "t.c"
    src.write_text(
        """
#define N 1
#undef N
int main(){ return N; }
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
    assert "#define" not in out
    assert "#undef" not in out
    # N should not be substituted after undef
    assert "return N;" in out
