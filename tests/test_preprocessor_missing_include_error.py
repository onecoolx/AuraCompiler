import subprocess
import sys
from pathlib import Path


def test_missing_include_error_mentions_search_paths(tmp_path: Path):
    src = tmp_path / "main.c"
    src.write_text('#include <definitely_missing_header_xyz.h>\n')

    res = subprocess.run(
        [sys.executable, "pycc.py", "-E", str(src)],
        cwd=Path(__file__).resolve().parents[1],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert res.returncode != 0
    msg = (res.stdout + "\n" + res.stderr).lower()
    assert "cannot find include" in msg
    assert "definitely_missing_header_xyz.h" in msg
    assert "searched" in msg or "search" in msg
