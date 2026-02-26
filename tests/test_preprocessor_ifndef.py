import subprocess
import sys
from pathlib import Path


def test_preprocessor_ifndef_true_when_undefined(tmp_path: Path):
    src = tmp_path / "main.c"
    src.write_text(
        (
            "#ifndef A\n"
            "int x = 1;\n"
            "#else\n"
            "int x = 2;\n"
            "#endif\n"
        )
    )

    res = subprocess.run(
        [sys.executable, "pycc.py", "-E", str(src)],
        cwd=Path(__file__).resolve().parents[1],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert res.returncode == 0, res.stderr
    assert "int x = 1;" in res.stdout
    assert "int x = 2;" not in res.stdout


def test_preprocessor_ifndef_false_when_defined(tmp_path: Path):
    src = tmp_path / "main.c"
    src.write_text(
        (
            "#define A 1\n"
            "#ifndef A\n"
            "int x = 1;\n"
            "#else\n"
            "int x = 2;\n"
            "#endif\n"
        )
    )

    res = subprocess.run(
        [sys.executable, "pycc.py", "-E", str(src)],
        cwd=Path(__file__).resolve().parents[1],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert res.returncode == 0, res.stderr
    assert "int x = 2;" in res.stdout
    assert "int x = 1;" not in res.stdout


def test_preprocessor_ifndef_tracks_undef(tmp_path: Path):
    src = tmp_path / "main.c"
    src.write_text(
        (
            "#define A 1\n"
            "#undef A\n"
            "#ifndef A\n"
            "int x = 3;\n"
            "#else\n"
            "int x = 4;\n"
            "#endif\n"
        )
    )

    res = subprocess.run(
        [sys.executable, "pycc.py", "-E", str(src)],
        cwd=Path(__file__).resolve().parents[1],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert res.returncode == 0, res.stderr
    assert "int x = 3;" in res.stdout
    assert "int x = 4;" not in res.stdout
