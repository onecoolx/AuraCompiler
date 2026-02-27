import os
import subprocess
import sys


def _pp(tmp_path, src: str) -> str:
    p = tmp_path / "t.c"
    p.write_text(src, encoding="utf-8")
    r = subprocess.run(
        [sys.executable, os.fspath(os.path.join(os.getcwd(), "pycc.py")), "-E", os.fspath(p)],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, (r.stdout, r.stderr)
    return r.stdout


def test_macro_self_recursive_object_like_terminates(tmp_path):
    out = _pp(
        tmp_path,
        """
#define A A
A
""".lstrip(),
    )
    # Must terminate. C-like behavior keeps it as A (not infinite expansion).
    assert out.strip() == "A"


def test_macro_mutual_recursion_terminates(tmp_path):
    out = _pp(
        tmp_path,
        """
#define A B
#define B A
A
""".lstrip(),
    )
    # Must terminate. With re-expansion suppression, it stabilizes.
    assert out.strip() in {"A", "B"}


def test_macro_self_recursive_function_like_terminates(tmp_path):
    out = _pp(
        tmp_path,
        """
#define F(x) F(x)
F(1)
""".lstrip(),
    )
    assert out.strip() == "F(1)"
