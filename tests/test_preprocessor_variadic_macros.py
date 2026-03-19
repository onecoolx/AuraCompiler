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


def test_E_variadic_macro_basic_substitution(tmp_path: Path):
    res = _run_E(
        tmp_path,
        r"""
#define V(fmt, ...) fmt, __VA_ARGS__
int x = V(1, 2, 3);
""".lstrip(),
    )
    assert res.returncode == 0, res.stderr
    assert "int x = 1, 2, 3;" in res.stdout


def test_E_variadic_macro_empty_va_args_is_allowed(tmp_path: Path):
    res = _run_E(
        tmp_path,
        r"""
#define V(fmt, ...) fmt __VA_ARGS__
int x = V(1);
""".lstrip(),
    )
    assert res.returncode == 0, res.stderr
    # Subset expectation: empty __VA_ARGS__ disappears (may leave extra whitespace).
    assert "int x = 1" in res.stdout


def test_E_variadic_macro_gnu_comma_swallow(tmp_path: Path):
    res = _run_E(
        tmp_path,
        r"""
#define LOG(fmt, ...) printf(fmt, ##__VA_ARGS__)
int a = LOG("%d", 1);
int b = LOG("hi");
""".lstrip(),
    )
    assert res.returncode == 0, res.stderr
    assert 'int a = printf("%d",1);' in res.stdout
    # When __VA_ARGS__ is empty, the preceding comma must be removed (GNU extension).
    assert 'int b = printf("hi");' in res.stdout


def test_E_variadic_macro_stringize_va_args(tmp_path: Path):
    res = _run_E(
        tmp_path,
        r"""
#define S(...) #__VA_ARGS__
const char *a = S(1, 2);
const char *b = S();
""".lstrip(),
    )
    assert res.returncode == 0, res.stderr
    # Non-empty: arguments are stringized (subset: whitespace normalization).
    assert 'const char *a = "1, 2";' in res.stdout
    # Empty: stringizes to empty string.
    assert 'const char *b = "";' in res.stdout
