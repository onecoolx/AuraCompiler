import subprocess
import sys
from pathlib import Path


def test_compile_path_honors_D_and_U(tmp_path: Path):
    src = tmp_path / "main.c"
    src.write_text(
        r"""
#if FLAG
int main(void) { return 1; }
#else
int main(void) { return 2; }
#endif
""".lstrip()
    )

    out = tmp_path / "a.out"

    # -DFLAG=1 selects true branch
    res1 = subprocess.run(
        [sys.executable, "pycc.py", "-DFLAG=1", str(src), "-o", str(out)],
        cwd=Path(__file__).resolve().parents[1],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert res1.returncode == 0, res1.stderr
    run1 = subprocess.run([str(out)])
    assert run1.returncode == 1

    # -DFLAG=1 -UFLAG removes it, selects else branch
    out2 = tmp_path / "b.out"
    res2 = subprocess.run(
        [sys.executable, "pycc.py", "-DFLAG=1", "-UFLAG", str(src), "-o", str(out2)],
        cwd=Path(__file__).resolve().parents[1],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert res2.returncode == 0, res2.stderr
    run2 = subprocess.run([str(out2)])
    assert run2.returncode == 2
