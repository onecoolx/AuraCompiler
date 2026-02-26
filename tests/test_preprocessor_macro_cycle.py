import subprocess
import sys
from pathlib import Path


def test_E_object_like_macro_self_cycle_terminates(tmp_path: Path):
    src = tmp_path / "t.c"
    src.write_text(
        (
            "#define A A\n"
            "int x = A;\n"
        )
    )

    res = subprocess.run(
        [sys.executable, "pycc.py", "-E", str(src)],
        cwd=Path(__file__).resolve().parents[1],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=5,
    )
    assert res.returncode == 0, res.stderr
    # Must not hang; output should stabilize.
    assert "int x = A;" in res.stdout


def test_E_object_like_macro_mutual_cycle_terminates(tmp_path: Path):
    src = tmp_path / "t.c"
    src.write_text(
        (
            "#define A B\n"
            "#define B A\n"
            "int x = A;\n"
        )
    )

    res = subprocess.run(
        [sys.executable, "pycc.py", "-E", str(src)],
        cwd=Path(__file__).resolve().parents[1],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=5,
    )
    assert res.returncode == 0, res.stderr
    # Either A or B is acceptable as long as expansion terminates.
    assert ("int x = A;" in res.stdout) or ("int x = B;" in res.stdout)
