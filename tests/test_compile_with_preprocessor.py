import subprocess
import sys
from pathlib import Path


def test_compile_path_runs_preprocessor(tmp_path: Path):
    inc = tmp_path / "inc"
    inc.mkdir()
    (inc / "cfg.h").write_text("#define RET 3\n")

    src = tmp_path / "main.c"
    src.write_text(
        r"""
#include <cfg.h>
#ifndef RET
#define RET 7
#endif
int main() { return RET; }
""".lstrip()
    )

    out = tmp_path / "a.out"
    res = subprocess.run(
        [sys.executable, "pycc.py", "-I", str(inc), str(src), "-o", str(out)],
        cwd=Path(__file__).resolve().parents[1],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert res.returncode == 0, res.stderr

    run = subprocess.run([str(out)])
    assert run.returncode == 3
