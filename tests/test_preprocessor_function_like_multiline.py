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


def test_E_function_like_define_multiline_body(tmp_path: Path):
    res = _run_E(
        tmp_path,
        (
            "#define F(x) (x) + \\\n"
            "  (x)\n"
            "int y = F(2);\n"
        ),
    )
    assert res.returncode == 0, res.stderr
    assert "int y" in res.stdout
    assert "2" in res.stdout
    assert "+" in res.stdout
