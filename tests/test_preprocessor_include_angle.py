import subprocess
import sys
from pathlib import Path


def test_preprocessor_E_include_angle_uses_I_paths(tmp_path: Path):
    repo_root = Path(__file__).resolve().parents[1]

    inc_dir = tmp_path / "inc"
    inc_dir.mkdir()
    (inc_dir / "mylib.h").write_text(
        """
#define N 9
""".lstrip()
    )

    src = tmp_path / "t.c"
    src.write_text(
        """
#include <mylib.h>
int main(){ return N; }
""".lstrip()
    )

    p = subprocess.run(
        [sys.executable, "pycc.py", "-E", "-I", str(inc_dir), str(src)],
        cwd=str(repo_root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert p.returncode == 0, p.stdout + p.stderr
    assert "return 9;" in p.stdout
