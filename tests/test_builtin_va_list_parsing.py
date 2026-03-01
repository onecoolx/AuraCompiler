import subprocess
import sys
from pathlib import Path


def test_builtin_va_list_typedef_parses(tmp_path):
    # Many system headers contain lines like:
    #   typedef __builtin_va_list __gnuc_va_list;
    # Our frontend should accept this token sequence.
    src = tmp_path / "t.c"
    src.write_text(
        """
        typedef __builtin_va_list __gnuc_va_list;
        int main(void) { return 0; }
        """.lstrip(),
        encoding="utf-8",
    )

    out = tmp_path / "a.out"
    res = subprocess.run(
        [sys.executable, "pycc.py", str(src), "-o", str(out)],
        cwd=Path(__file__).resolve().parents[1],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert res.returncode == 0, (res.stdout + res.stderr)
