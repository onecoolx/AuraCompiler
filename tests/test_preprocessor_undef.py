import subprocess
import sys
from pathlib import Path


def test_preprocessor_undef_object_like_macro_removes_expansion(tmp_path: Path):
    src = tmp_path / "main.c"
    src.write_text(
        (
            "#define A 123\n"
            "int x = A;\n"
            "#undef A\n"
            "int y = A;\n"
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
    assert "int x = 123;" in res.stdout
    assert "int y = A;" in res.stdout


def test_preprocessor_undef_function_like_macro_removes_expansion(tmp_path: Path):
    src = tmp_path / "main.c"
    src.write_text(
        (
            "#define F(x) x\n"
            "int a = F(1);\n"
            "#undef F\n"
            "int b = F(2);\n"
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
    assert "int a = 1;" in res.stdout
    assert "int b = F(2);" in res.stdout
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
