import subprocess
import sys
from pathlib import Path


def _run_E(cwd: Path, src: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "pycc.py", "-E", str(src)],
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def test_preprocessor_E_include_operand_is_macro_expanded(tmp_path: Path):
    repo_root = Path(__file__).resolve().parents[1]

    inc = tmp_path / "a.h"
    inc.write_text("int A = 1;\n")

    src = tmp_path / "t.c"
    src.write_text(
        (
            '#define HEADER "a.h"\n'
            "#include HEADER\n"
            "int main(){ return A; }\n"
        )
    )

    res = _run_E(repo_root, src)
    assert res.returncode == 0, res.stdout + res.stderr
    assert '#include HEADER' not in res.stdout
    assert 'int A = 1;' in res.stdout


def test_preprocessor_E_include_operand_is_function_like_macro_expanded(tmp_path: Path):
    repo_root = Path(__file__).resolve().parents[1]

    inc = tmp_path / "b.h"
    inc.write_text("int B = 2;\n")

    src = tmp_path / "t.c"
    src.write_text(
        (
            '#define STR(x) x\n'
            '#define HDR STR("b.h")\n'
            "#include HDR\n"
            "int main(){ return B; }\n"
        )
    )

    res = _run_E(repo_root, src)
    assert res.returncode == 0, res.stdout + res.stderr
    assert '#include HDR' not in res.stdout
    assert 'int B = 2;' in res.stdout
