import subprocess
import sys
from pathlib import Path


def _compile_and_run(tmp_path: Path, code: str) -> int:
    src = tmp_path / "t.c"
    out = tmp_path / "t"
    src.write_text(code.lstrip())

    repo = Path(__file__).resolve().parents[1]
    res = subprocess.run(
        [sys.executable, "pycc.py", str(src), "-o", str(out)],
        cwd=repo,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert res.returncode == 0, res.stderr

    run = subprocess.run([str(out)], check=False)
    return run.returncode


def test_unsigned_char_assignment_truncates(tmp_path: Path) -> None:
    code = r"""
int main(){
  unsigned char c;
  c = 300; /* 300 mod 256 = 44 */
  return (c == (unsigned char)44) ? 0 : 1;
}
"""
    assert _compile_and_run(tmp_path, code) == 0


def test_unsigned_short_assignment_truncates(tmp_path: Path) -> None:
    code = r"""
int main(){
  unsigned short s;
  s = 70000; /* 70000 mod 65536 = 4464 */
  return (s == (unsigned short)4464) ? 0 : 1;
}
"""
    assert _compile_and_run(tmp_path, code) == 0


def test_short_assignment_truncates(tmp_path: Path) -> None:
    code = r"""
int main(){
  short s;
  s = 0x12345; /* truncated to 0x2345 */
  return (s == (short)0x2345) ? 0 : 1;
}
"""
    assert _compile_and_run(tmp_path, code) == 0
