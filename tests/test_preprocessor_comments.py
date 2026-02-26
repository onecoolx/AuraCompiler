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


def test_E_strips_line_and_block_comments(tmp_path: Path):
    res = _run_E(
        tmp_path,
        r"""
#define N 7 /* trailing block comment */
// whole-line comment
int main(){
  return N; // comment after code
}
""".lstrip(),
    )
    assert res.returncode == 0, res.stderr
    assert "//" not in res.stdout
    assert "/*" not in res.stdout
    assert "return 7;" in res.stdout


def test_E_if_with_block_comment(tmp_path: Path):
    res = _run_E(
        tmp_path,
        r"""
#if 1 /* comment */
int x = 1;
#else
int x = 2;
#endif
""".lstrip(),
    )
    assert res.returncode == 0, res.stderr
    assert "int x = 1;" in res.stdout
    assert "int x = 2;" not in res.stdout


def test_E_multiline_block_comment_is_stripped(tmp_path: Path):
    res = _run_E(
        tmp_path,
        r"""
/* start
   middle */
int x = 1;
""".lstrip(),
    )
    assert res.returncode == 0, res.stderr
    assert "/*" not in res.stdout
    assert "int x = 1;" in res.stdout


def test_E_does_not_strip_comment_markers_in_strings(tmp_path: Path):
    res = _run_E(
        tmp_path,
        r"""
const char *s = "/* not a comment */ // still not";
int main(){ return 0; }
""".lstrip(),
    )
    assert res.returncode == 0, res.stderr
    assert '"/* not a comment */ // still not"' in res.stdout
