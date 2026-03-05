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


def test_unsigned_char_pointer_compound_add_assign(tmp_path: Path) -> None:
    # (*p) += 2 should truncate to unsigned char on store.
    code = r"""
int main(){
  unsigned char a[1];
  unsigned char *p = a;
  *p = 255;
  *p += 2;
  return (a[0] == (unsigned char)1) ? 0 : 1;
}
"""
    assert _compile_and_run(tmp_path, code) == 0


def test_unsigned_char_pointer_compound_rshift_assign(tmp_path: Path) -> None:
    # Unsigned >>= should be logical.
    code = r"""
int main(){
  unsigned char a[1];
  unsigned char *p = a;
  *p = (unsigned char)0xFF;
  *p >>= 1;
  return (a[0] == (unsigned char)0x7F) ? 0 : 1;
}
"""
    assert _compile_and_run(tmp_path, code) == 0


def test_short_pointer_compound_rshift_assign(tmp_path: Path) -> None:
    # Signed >>= should be arithmetic on this target.
    code = r"""
int main(){
  short a[1];
  short *p = a;
  *p = (short)-1;
  *p >>= 1;
  return (a[0] == (short)-1) ? 0 : 1;
}
"""
    assert _compile_and_run(tmp_path, code) == 0
