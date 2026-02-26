import subprocess
import sys
from pathlib import Path


def _run_E(tmp_path: Path, text: str) -> subprocess.CompletedProcess:
    c_path = tmp_path / "t.c"
    c_path.write_text(text)
    return subprocess.run(
        [sys.executable, "pycc.py", "-E", str(c_path)],
        cwd=Path(__file__).resolve().parents[1],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def test_E_function_like_macro_single_param(tmp_path: Path):
    res = _run_E(
        tmp_path,
        r"""
#define F(x) x + 1
int main(){
  return F(2);
}
""".lstrip(),
    )
    assert res.returncode == 0, res.stderr
    assert "return 2 + 1;" in res.stdout


def test_E_function_like_macro_multiple_params(tmp_path: Path):
    res = _run_E(
        tmp_path,
        r"""
#define ADD(a,b) (a) + (b)
int main(){
  return ADD(3, 4);
}
""".lstrip(),
    )
    assert res.returncode == 0, res.stderr
    assert "return (3) + (4);" in res.stdout


def test_E_function_like_macro_nested_invocation(tmp_path: Path):
    res = _run_E(
        tmp_path,
        r"""
#define INC(x) (x) + 1
#define ADD(a,b) (a) + (b)
int main(){
  return ADD(INC(1), INC(2));
}
""".lstrip(),
    )
    assert res.returncode == 0, res.stderr
    # Best-effort expansion should expand nested calls too.
    assert "return ((1) + 1) + ((2) + 1);" in res.stdout
