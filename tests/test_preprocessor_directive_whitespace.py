import subprocess
import sys
from pathlib import Path


def _run_E(tmp_path: Path, text: str) -> subprocess.CompletedProcess:
    c_path = tmp_path / "t.c"
    c_path.write_text(text)
    return subprocess.run(
        [sys.executable, "pycc.py", "-E", str(c_path)],
        cwd=Path(__file__).resolve().parents[1],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def test_E_whitespace_in_define_and_if(tmp_path: Path):
    res = _run_E(
        tmp_path,
        (
            "#\tdefine   X\t  1\n"
            "#   if\tX\n"
            "int x = 1;\n"
            "#  else\n"
            "int x = 2;\n"
            "#\tendif\n"
        ),
    )
    assert res.returncode == 0, res.stderr
    assert "int x = 1;" in res.stdout
    assert "int x = 2;" not in res.stdout


def test_E_whitespace_in_include_quote(tmp_path: Path):
    inc = tmp_path / "inc"
    inc.mkdir()
    (inc / "a.h").write_text("int a = 1;\n")

    src = tmp_path / "t.c"
    src.write_text('#  include   "a.h"\n')

    res = subprocess.run(
        [sys.executable, "pycc.py", "-E", "-I", str(inc), str(src)],
        cwd=Path(__file__).resolve().parents[1],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert res.returncode == 0, res.stderr
    assert "int a = 1;" in res.stdout
