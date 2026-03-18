import subprocess
import sys
import textwrap
from pathlib import Path


def _run_E(cwd: Path, src: Path):
    return subprocess.run(
        [sys.executable, "pycc.py", "-E", str(src)],
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def test_missing_include_mentions_includer_file_and_line(tmp_path: Path):
    src = tmp_path / "main.c"
    src.write_text(
        textwrap.dedent(
            """
            int x;
            #include "missing.h"
            int y;
            """
        ).lstrip()
    )

    repo_root = Path(__file__).resolve().parents[1]
    res = _run_E(repo_root, src)

    assert res.returncode != 0
    msg = (res.stdout + "\n" + res.stderr).lower()

    assert "cannot find include" in msg
    assert "missing.h" in msg
    # Location should point at the includer source + line number.
    assert "main.c" in msg
    assert ":2" in msg


def test_missing_include_mentions_include_stack_order(tmp_path: Path):
    # main.c -> a.h -> missing.h
    (tmp_path / "a.h").write_text('#include "missing.h"\n', encoding="utf-8")

    src = tmp_path / "main.c"
    src.write_text('#include "a.h"\n', encoding="utf-8")

    repo_root = Path(__file__).resolve().parents[1]
    res = _run_E(repo_root, src)

    assert res.returncode != 0
    msg = (res.stdout + "\n" + res.stderr).lower()

    assert "cannot find include" in msg
    assert "include stack" in msg
    # Ensure order is outer -> inner.
    assert "main.c" in msg
    assert "a.h" in msg
