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


def test_unsigned_char_compound_add_assign_truncates(tmp_path: Path) -> None:
    # unsigned char wraps modulo 256 on assignment.
    code = r"""
int main(){
  unsigned char c = 255;
  c += 2;
  return (c == (unsigned char)1) ? 0 : 1;
}
"""
    assert _compile_and_run(tmp_path, code) == 0


def test_unsigned_short_compound_add_assign_truncates(tmp_path: Path) -> None:
    # unsigned short wraps modulo 65536 on assignment.
    code = r"""
int main(){
  unsigned short s = 65535;
  s += 2;
  return (s == (unsigned short)1) ? 0 : 1;
}
"""
    assert _compile_and_run(tmp_path, code) == 0


def test_short_compound_add_assign_truncates(tmp_path: Path) -> None:
    # signed short assignment truncates to 16-bit (two's complement).
    code = r"""
int main(){
  short s = 32767;
  s += 2;
  return (s == (short)-32767) ? 0 : 1;
}
"""
    assert _compile_and_run(tmp_path, code) == 0


def test_unsigned_char_compound_or_assign_truncates(tmp_path: Path) -> None:
        # Operate in int, then convert back to unsigned char.
        code = r"""
int main(){
    unsigned char c = 0;
    c |= 0x1FF; /* 0xFF after truncation */
    return (c == (unsigned char)0xFF) ? 0 : 1;
}
"""
        assert _compile_and_run(tmp_path, code) == 0


def test_unsigned_char_compound_lshift_assign_truncates(tmp_path: Path) -> None:
        # (unsigned char)0x80 << 1 => 0x100 -> trunc to 0
        code = r"""
int main(){
    unsigned char c = 0x80;
    c <<= 1;
    return (c == (unsigned char)0) ? 0 : 1;
}
"""
        assert _compile_and_run(tmp_path, code) == 0


def test_unsigned_short_compound_or_assign_truncates(tmp_path: Path) -> None:
        code = r"""
int main(){
    unsigned short s = 0;
    s |= 0x1FFFF; /* 0xFFFF after truncation */
    return (s == (unsigned short)0xFFFF) ? 0 : 1;
}
"""
        assert _compile_and_run(tmp_path, code) == 0


def test_unsigned_short_compound_lshift_assign_truncates(tmp_path: Path) -> None:
        # 0x8000 << 1 => 0x10000 -> trunc to 0
        code = r"""
int main(){
    unsigned short s = 0x8000;
    s <<= 1;
    return (s == (unsigned short)0) ? 0 : 1;
}
"""
        assert _compile_and_run(tmp_path, code) == 0


def test_signed_short_compound_rshift_assign_keeps_sign(tmp_path: Path) -> None:
        # Implementation-defined in C89, but on x86-64 sar is expected.
        code = r"""
int main(){
    short s = (short)-1;
    s >>= 1;
    return (s == (short)-1) ? 0 : 1;
}
"""
        assert _compile_and_run(tmp_path, code) == 0
