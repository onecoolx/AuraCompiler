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


def test_u64_div_is_unsigned(tmp_path: Path) -> None:
    # Unsigned division: ULONG_MAX / 2 = 0x7fffffffffffffff
    code = r"""
int main(){
  unsigned long u = 0xffffffffffffffffUL;
  return (int)((u / 2UL) == 0x7fffffffffffffffUL);
}
"""
    assert _compile_and_run(tmp_path, code) == 1


def test_u64_mod_is_unsigned(tmp_path: Path) -> None:
    # Unsigned modulo: ULONG_MAX % 2 = 1
    code = r"""
int main(){
  unsigned long u = 0xffffffffffffffffUL;
  return (int)((u % 2UL) == 1UL);
}
"""
    assert _compile_and_run(tmp_path, code) == 1


def test_mixed_signed_long_unsigned_long_compare_is_unsigned(tmp_path: Path) -> None:
    # Usual arithmetic conversions: unsigned long vs long => unsigned long.
    # So -1L converts to ULONG_MAX and is > 0UL.
    code = r"""
int main(){
  unsigned long u = 1UL;
  long s = -1L;
  return (int)((0 ? u : s) > 0UL);
}
"""
    assert _compile_and_run(tmp_path, code) == 1


def test_mixed_signed_long_unsigned_long_add_is_u64(tmp_path: Path) -> None:
    # 1UL + (-1L) => 0 (unsigned long arithmetic)
    code = r"""
int main(){
  unsigned long u = 1UL;
  long s = -1L;
  return (int)((u + s) == 0UL);
}
"""
    assert _compile_and_run(tmp_path, code) == 1
