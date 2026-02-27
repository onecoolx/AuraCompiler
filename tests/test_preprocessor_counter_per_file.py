import subprocess
import sys
from pathlib import Path


def run_E(args, cwd):
    return subprocess.run(args, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def test___COUNTER____per_file_for_includes(tmp_path: Path):
    inc = tmp_path / "inc"
    inc.mkdir()
    (inc / "hdr.h").write_text("int a = __COUNTER__;\nint b = __COUNTER__;\n")

    src = tmp_path / "main.c"
    src.write_text('#include "hdr.h"\nint c = __COUNTER__;\n')

    res = run_E([sys.executable, "pycc.py", "-E", str(src), "-I", str(inc)], cwd=Path(__file__).resolve().parents[1])
    assert res.returncode == 0, res.stderr
    out = res.stdout
    # header should have 0,1 and main.c counter starts at 0
    assert "int a = 0;" in out
    assert "int b = 1;" in out
    assert "int c = 0;" in out
