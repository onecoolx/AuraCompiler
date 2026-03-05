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


def test_unsigned_char_local_promotes_with_zero_extend(tmp_path: Path) -> None:
    code = r"""
int main(){
  unsigned char c = 255;
  /* if sign-extended, becomes -1 and the compare fails */
  return ((int)c == 255) ? 0 : 1;
}
"""
    assert _compile_and_run(tmp_path, code) == 0


def test_unsigned_short_local_promotes_with_zero_extend(tmp_path: Path) -> None:
    code = r"""
int main(){
  unsigned short s = 65535;
  return ((int)s == 65535) ? 0 : 1;
}
"""
    assert _compile_and_run(tmp_path, code) == 0


def test_unsigned_char_pointer_load_zero_extend(tmp_path: Path) -> None:
    code = r"""
int main(){
  unsigned char a[2];
  a[0] = 255;
  unsigned char *p = a;
  int x = (int)(*p);
  return (x == 255) ? 0 : 1;
}
"""
    assert _compile_and_run(tmp_path, code) == 0


def test_unsigned_short_pointer_load_zero_extend(tmp_path: Path) -> None:
    code = r"""
int main(){
  unsigned short a[2];
  a[0] = 65535;
  unsigned short *p = a;
  int x = (int)(*p);
  return (x == 65535) ? 0 : 1;
}
"""
    assert _compile_and_run(tmp_path, code) == 0


def test_signed_short_pointer_load_sign_extend(tmp_path: Path) -> None:
    code = r"""
int main(){
  short a[2];
  a[0] = (short)0xFFFF;
  short *p = a;
  int x = (int)(*p);
  return (x == -1) ? 0 : 1;
}
"""
    assert _compile_and_run(tmp_path, code) == 0
