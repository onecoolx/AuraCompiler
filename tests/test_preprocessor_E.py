import subprocess
from pathlib import Path


def test_preprocessor_E_passthrough_stdout(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]

    src = tmp_path / "t.c"
    src.write_text(
        """
int main(){
  return 0;
}
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
    assert p.stdout.strip() == src.read_text().strip()


def test_preprocessor_E_passthrough_to_file(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]

    src = tmp_path / "t.c"
    out = tmp_path / "t.i"
    src.write_text(
        """
int x = 1;
int main(){ return x; }
""".lstrip()
    )

    p = subprocess.run(
        ["python", "pycc.py", "-E", str(src), "-o", str(out)],
        cwd=str(repo_root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert p.returncode == 0, p.stdout + p.stderr
    assert out.read_text().strip() == src.read_text().strip()
