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


def test___COUNTER___increments_sequentially(tmp_path: Path):
    res = _run_E(
        tmp_path,
        (
            "int a = __COUNTER__;\n"
            "int b = __COUNTER__;\n"
            "int c = __COUNTER__;\n"
        ),
    )
    assert res.returncode == 0, res.stderr
    assert "int a = 0;" in res.stdout
    assert "int b = 1;" in res.stdout
    assert "int c = 2;" in res.stdout


def test___COUNTER____in_function_like_macro(tmp_path: Path):
    res = _run_E(
        tmp_path,
        (
            "#define M() __COUNTER__\n"
            "int x = M();\n"
            "int y = M();\n"
            "int z = __COUNTER__;\n"
        ),
    )
    assert res.returncode == 0, res.stderr
    # M() should produce 0, then 1, then standalone __COUNTER__ should be 2
    assert "int x = 0;" in res.stdout
    assert "int y = 1;" in res.stdout
    assert "int z = 2;" in res.stdout
