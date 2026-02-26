import subprocess
import sys
from pathlib import Path


def _pp(tmp_path: Path, text: str):
    src = tmp_path / "main.c"
    src.write_text(text)
    return subprocess.run(
        [sys.executable, "pycc.py", "-E", str(src)],
        cwd=Path(__file__).resolve().parents[1],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def test_preprocessor_elifdef_selects_defined_branch(tmp_path: Path):
    res = _pp(
        tmp_path,
        (
            "#define A 1\n"
            "#if 0\n"
            "int x = 0;\n"
            "#elifdef A\n"
            "int x = 1;\n"
            "#else\n"
            "int x = 2;\n"
            "#endif\n"
        ),
    )
    assert res.returncode == 0, res.stderr
    assert "int x = 1;" in res.stdout
    assert "int x = 0;" not in res.stdout
    assert "int x = 2;" not in res.stdout


def test_preprocessor_elifndef_selects_undefined_branch(tmp_path: Path):
    res = _pp(
        tmp_path,
        (
            "#define A 1\n"
            "#if 0\n"
            "int x = 0;\n"
            "#elifndef B\n"
            "int x = 1;\n"
            "#else\n"
            "int x = 2;\n"
            "#endif\n"
        ),
    )
    assert res.returncode == 0, res.stderr
    assert "int x = 1;" in res.stdout
    assert "int x = 0;" not in res.stdout
    assert "int x = 2;" not in res.stdout


def test_preprocessor_elifdef_respects_taken_branch(tmp_path: Path):
    res = _pp(
        tmp_path,
        (
            "#define A 1\n"
            "#if 1\n"
            "int x = 0;\n"
            "#elifdef A\n"
            "int x = 1;\n"
            "#else\n"
            "int x = 2;\n"
            "#endif\n"
        ),
    )
    assert res.returncode == 0, res.stderr
    assert "int x = 0;" in res.stdout
    assert "int x = 1;" not in res.stdout
    assert "int x = 2;" not in res.stdout
