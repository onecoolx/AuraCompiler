import os
import shutil
import subprocess
import sys
from pathlib import Path


def _run_pycc(args, cwd: Path):
    return subprocess.run(
        [sys.executable, "pycc.py", *args],
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def test_E_builtin_preprocessor_outputs_expansion(tmp_path: Path):
    """-E should use the built-in preprocessor by default."""

    inc = tmp_path / "inc"
    inc.mkdir()
    (inc / "cfg.h").write_text("#define RET 5\n")

    src = tmp_path / "main.c"
    src.write_text(
        (
            "#include <cfg.h>\n"
            "int main() { return RET; }\n"
        )
    )

    repo = Path(__file__).resolve().parents[1]
    res = _run_pycc(["-E", "-I", str(inc), str(src)], cwd=repo)
    assert res.returncode == 0, res.stderr
    assert "RET" not in res.stdout
    assert "return 5" in res.stdout


def test_E_system_cpp_outputs_expansion_if_available(tmp_path: Path):
    """--use-system-cpp -E should work when gcc is available.

    Skips in minimal environments.
    """

    if shutil.which("gcc") is None:
        return

    inc = tmp_path / "inc"
    inc.mkdir()
    (inc / "cfg.h").write_text("#define RET 6\n")

    src = tmp_path / "main.c"
    src.write_text(
        (
            "#include <cfg.h>\n"
            "int main() { return RET; }\n"
        )
    )

    repo = Path(__file__).resolve().parents[1]
    res = _run_pycc(["-E", "--use-system-cpp", "-I", str(inc), str(src)], cwd=repo)
    assert res.returncode == 0, res.stderr
    assert "RET" not in res.stdout
    assert "return 6" in res.stdout


def test_compile_builtin_vs_system_cpp_same_result(tmp_path: Path):
    """Compiling with built-in vs system preprocessor should be equivalent for simple cases."""

    if shutil.which("gcc") is None:
        return

    inc = tmp_path / "inc"
    inc.mkdir()
    (inc / "cfg.h").write_text("#define RET 11\n")

    src = tmp_path / "main.c"
    src.write_text(
        (
            "#include <cfg.h>\n"
            "int main() { return RET; }\n"
        )
    )

    repo = Path(__file__).resolve().parents[1]

    out1 = tmp_path / "a_builtin.out"
    res1 = _run_pycc(["-I", str(inc), str(src), "-o", str(out1)], cwd=repo)
    assert res1.returncode == 0, res1.stderr

    out2 = tmp_path / "a_system.out"
    res2 = _run_pycc(["--use-system-cpp", "-I", str(inc), str(src), "-o", str(out2)], cwd=repo)
    assert res2.returncode == 0, res2.stderr

    run1 = subprocess.run([str(out1)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert run1.returncode == 11

    run2 = subprocess.run([str(out2)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert run2.returncode == 11
