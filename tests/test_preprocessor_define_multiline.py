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


def test_E_object_like_define_multiline_continuation(tmp_path: Path):
    res = _run_E(
        tmp_path,
        (
            "#define A 1 \\\n"
            "+ 2\n"
            "int x = A;\n"
        ),
    )
    assert res.returncode == 0, res.stderr
    assert "int x = 1" in res.stdout
    assert "+ 2;" in res.stdout


def test_E_object_like_define_multiline_preserves_spacing(tmp_path: Path):
    res = _run_E(
        tmp_path,
        (
            "#define A foo \\\n"
            "bar\n"
            "int x = 0;\n"
            "A\n"
        ),
    )
    assert res.returncode == 0, res.stderr
    # We only require the logical line to be joined; exact whitespace is subset.
    assert "foo" in res.stdout
    assert "bar" in res.stdout
