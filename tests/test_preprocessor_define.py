import subprocess
from pathlib import Path


def test_preprocessor_E_object_like_define_substitution(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]

    src = tmp_path / "t.c"
    src.write_text(
        """
#define N 42
int main(){
  return N;
}
""".lstrip()
    )

    p = subprocess.run(
        ["python", "pycc.py", "-E", str(src)],
        cwd=str(repo_root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert p.returncode == 0, p.stdout + p.stderr

    out = p.stdout
    assert "#define" not in out
    assert "return 42;" in out


def test_preprocessor_E_define_then_include_sees_macro(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]

    inc = tmp_path / "a.h"
    src = tmp_path / "t.c"

    inc.write_text(
        """
int get(void){
  return N;
}
""".lstrip()
    )

    src.write_text(
        """
#define N 7
#include "a.h"
int main(){
  return get();
}
""".lstrip()
    )

    p = subprocess.run(
        ["python", "pycc.py", "-E", str(src)],
        cwd=str(repo_root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert p.returncode == 0, p.stdout + p.stderr

    out = p.stdout
    assert "#define" not in out
    assert "return 7;" in out
