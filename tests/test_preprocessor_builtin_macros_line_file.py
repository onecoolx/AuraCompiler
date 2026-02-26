import subprocess
import sys
from pathlib import Path


def _run_E(cwd: Path, src: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "pycc.py", "-E", str(src)],
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def test_E_builtin___LINE___expands(tmp_path: Path):
    # Ensure __LINE__ corresponds to the physical line number in the file.
    src = tmp_path / "t.c"
    src.write_text(
        (
            "int a = __LINE__;\n"  # line 1
            "int b = __LINE__;\n"  # line 2
        )
    )
    res = _run_E(Path(__file__).resolve().parents[1], src)
    assert res.returncode == 0, res.stderr
    assert "int a = 1;" in res.stdout
    assert "int b = 2;" in res.stdout


def test_E_builtin___FILE___expands_to_quoted_string(tmp_path: Path):
    src = tmp_path / "t.c"
    src.write_text("const char *p = __FILE__;\n")
    res = _run_E(Path(__file__).resolve().parents[1], src)
    assert res.returncode == 0, res.stderr
    # Subset: accept either basename or full path, but must be a C string literal.
    assert 'const char *p = "' in res.stdout
    assert '";' in res.stdout
