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


def test_u32_add_wraps_mod_2_32(tmp_path: Path) -> None:
    # UINT_MAX + 1 wraps to 0.
    code = r"""
int main(){
  unsigned int u = 0xffffffffU;
  return (int)((u + 1U) == 0U);
}
"""
    assert _compile_and_run(tmp_path, code) == 1


def test_u32_sub_wraps_mod_2_32(tmp_path: Path) -> None:
    # 0 - 1U wraps to UINT_MAX.
    code = r"""
int main(){
  unsigned int u = 0U;
  return (int)((u - 1U) == 0xffffffffU);
}
"""
    assert _compile_and_run(tmp_path, code) == 1


def test_u32_mul_wraps_mod_2_32(tmp_path: Path) -> None:
    # 0x80000000 * 2 wraps to 0.
    code = r"""
int main(){
  unsigned int u = 0x80000000U;
  return (int)((u * 2U) == 0U);
}
"""
    assert _compile_and_run(tmp_path, code) == 1


def test_u32_div_is_unsigned(tmp_path: Path) -> None:
    # Unsigned division: UINT_MAX / 2 = 0x7fffffff.
    code = r"""
int main(){
  unsigned int u = 0xffffffffU;
  return (int)((u / 2U) == 0x7fffffffU);
}
"""
    assert _compile_and_run(tmp_path, code) == 1


def test_u32_mod_is_unsigned(tmp_path: Path) -> None:
    # Unsigned modulo: UINT_MAX % 2 = 1.
    code = r"""
int main(){
  unsigned int u = 0xffffffffU;
  return (int)((u % 2U) == 1U);
}
"""
    assert _compile_and_run(tmp_path, code) == 1


def test_mixed_signed_unsigned_arithmetic_uses_u32(tmp_path: Path) -> None:
    # If either operand is unsigned int, the other is converted to unsigned int.
    # 1U + (-1) == 0 (mod 2^32)
    code = r"""
int main(){
  unsigned int u = 1U;
  int i = -1;
  return (int)((u + i) == 0U);
}
"""
    assert _compile_and_run(tmp_path, code) == 1
