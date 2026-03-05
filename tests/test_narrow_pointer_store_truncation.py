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


def test_unsigned_char_pointer_store_truncates(tmp_path: Path) -> None:
    code = r"""
int main(){
  unsigned char a[1];
  unsigned char *p = a;
  *p = 300;
  return (a[0] == (unsigned char)44) ? 0 : 1;
}
"""
    assert _compile_and_run(tmp_path, code) == 0


def test_unsigned_short_pointer_store_truncates(tmp_path: Path) -> None:
    code = r"""
int main(){
  unsigned short a[1];
  unsigned short *p = a;
  *p = 70000;
  return (a[0] == (unsigned short)4464) ? 0 : 1;
}
"""
    assert _compile_and_run(tmp_path, code) == 0


def test_short_pointer_store_truncates(tmp_path: Path) -> None:
    code = r"""
int main(){
  short a[1];
  short *p = a;
  *p = 0x12345;
  return (a[0] == (short)0x2345) ? 0 : 1;
}
"""
    assert _compile_and_run(tmp_path, code) == 0
