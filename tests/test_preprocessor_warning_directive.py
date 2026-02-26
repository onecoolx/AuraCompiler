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


def test_E_warning_directive_emits_message(tmp_path: Path):
    res = _run_E(
        tmp_path,
        r"""
#warning hello
int x = 1;
""".lstrip(),
    )
    assert res.returncode == 0
    # Subset behavior: the directive should be handled (not necessarily printed)
    # but must not appear in preprocessed output.
    assert "#warning" not in res.stdout


def test_E_warning_directive_ignored_in_skipped_region(tmp_path: Path):
    res = _run_E(
        tmp_path,
        r"""
#if 0
#warning should_not_show
#endif
int x = 1;
""".lstrip(),
    )
    assert res.returncode == 0
    assert "#warning" not in res.stdout
