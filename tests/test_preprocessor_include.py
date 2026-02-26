import subprocess
from pathlib import Path


def test_preprocessor_E_local_include_quotes(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]

    inc = tmp_path / "a.h"
    src = tmp_path / "t.c"

    inc.write_text(
        """
int get(void){
  return 42;
}
""".lstrip()
    )

    src.write_text(
        """
#include "a.h"
int main(){
  return get() == 42 ? 0 : 1;
}
""".lstrip()
    )

    # -E should inline the include.
    p = subprocess.run(
        ["python", "pycc.py", "-E", str(src)],
        cwd=str(repo_root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert p.returncode == 0, p.stdout + p.stderr

    out = p.stdout
    assert "#include \"a.h\"" not in out
    assert "int get(void)" in out
    assert "int main()" in out
