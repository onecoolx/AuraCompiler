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


def test_unsigned_right_shift_is_logical_u32(tmp_path: Path) -> None:
    # 0xffffffffU >> 31 == 1 (logical shift)
    code = r"""
int main(){
  unsigned int u = 0xffffffffU;
  return (int)((u >> 31) == 1U);
}
"""
    assert _compile_and_run(tmp_path, code) == 1


def test_signed_right_shift_keeps_sign_for_negative_int(tmp_path: Path) -> None:
    # Implementation-defined in C89, but on x86-64 arithmetic shift is expected.
    # -1 >> 1 stays -1.
    code = r"""
int main(){
  int i = -1;
  return (int)((i >> 1) == -1);
}
"""
    assert _compile_and_run(tmp_path, code) == 1


def test_mixed_unsigned_int_and_int_shift_uses_unsigned_u32(tmp_path: Path) -> None:
    # Usual arithmetic conversions: if one operand is unsigned int, the other is converted.
    # (-1) becomes UINT_MAX, then >> 31 yields 1.
    code = r"""
int main(){
  unsigned int u = 0U;
  int i = -1;
  return (int)(((u + i) >> 31) == 1U);
}
"""
    assert _compile_and_run(tmp_path, code) == 1


def test_bitwise_or_mixed_signed_unsigned_is_u32(tmp_path: Path) -> None:
    # (unsigned)0 | (-1) == UINT_MAX
    code = r"""
int main(){
  unsigned int u = 0U;
  int i = -1;
  return (int)((u | i) == 0xffffffffU);
}
"""
    assert _compile_and_run(tmp_path, code) == 1
