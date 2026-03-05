import subprocess
import sys
from pathlib import Path


def _compile_and_run(tmp_path: Path, c_src: str) -> int:
    src = tmp_path / "main.c"
    src.write_text(c_src.lstrip())
    out = tmp_path / "a.out"

    repo = Path(__file__).resolve().parents[1]
    res = subprocess.run(
        [sys.executable, "pycc.py", str(src), "-o", str(out)],
        cwd=repo,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert res.returncode == 0, res.stderr

    run = subprocess.run([str(out)])
    return run.returncode


def test_uac_unsigned_int_dominates_signed_int_negative(tmp_path: Path) -> None:
    # C usual arithmetic conversions:
    #   int (-1) converted to unsigned int => UINT_MAX
    #   UINT_MAX + 1 wraps to 0
    c = r"""
unsigned int u = 1U;
int i = -1;
int main() {
  return (int)((u + i) == 0U);
}
"""
    # Expect true => return 1
    assert _compile_and_run(tmp_path, c) == 1


def test_uac_relational_uses_unsigned_when_mixed(tmp_path: Path) -> None:
    # If mixed signed/unsigned of same rank, compare as unsigned.
    # (unsigned)1 > (unsigned)-1 is false.
    c = r"""
unsigned int u = 1U;
int i = -1;
int main() {
  return (int)(u > i);
}
"""
    assert _compile_and_run(tmp_path, c) == 0


def test_integer_promotion_char_to_int_in_expression(tmp_path: Path) -> None:
    # Ensure signed char promotes to int before arithmetic.
    c = r"""
int main() {
  signed char c = (signed char)-1;
  return (int)((c + 1) == 0);
}
"""
    assert _compile_and_run(tmp_path, c) == 1
