"""Tests for cross-TU type compatibility checking (C89 §6.1.2.6)."""
import subprocess
from pathlib import Path
from pycc.compiler import Compiler


def _multi_tu_compile(tmp_path, files, output="out"):
    """Compile multiple C files together."""
    paths = []
    for name, code in files.items():
        p = tmp_path / name
        p.write_text(code)
        paths.append(str(p))
    out = tmp_path / output
    comp = Compiler(optimize=False)
    return comp.compile_files(paths, str(out))


def test_compatible_function_across_tus(tmp_path):
    """Same function prototype in two TUs should link fine."""
    res = _multi_tu_compile(tmp_path, {
        "a.c": "int add(int a, int b) { return a + b; }\n",
        "b.c": "int add(int a, int b);\nint main(void) { return add(1,2) == 3 ? 0 : 1; }\n",
    })
    assert res.success, f"Expected success: {res.errors}"
    p = subprocess.run([str(tmp_path / "out")], check=False, timeout=5)
    assert p.returncode == 0


def test_incompatible_return_type_across_tus(tmp_path):
    """Different return types for same function across TUs should fail."""
    res = _multi_tu_compile(tmp_path, {
        "a.c": "int foo(void) { return 0; }\n",
        "b.c": "void foo(void);\nint main(void) { foo(); return 0; }\n",
    })
    assert not res.success
    assert any("incompatible" in e for e in res.errors)


def test_incompatible_param_type_across_tus(tmp_path):
    """Different parameter types for same function across TUs should fail."""
    res = _multi_tu_compile(tmp_path, {
        "a.c": "int process(int x) { return x + 1; }\n",
        "b.c": "int process(char *s);\nint main(void) { return 0; }\n",
    })
    assert not res.success
    assert any("incompatible" in e.lower() for e in res.errors)


def test_incompatible_global_type_across_tus(tmp_path):
    """Different types for same global variable across TUs should fail."""
    res = _multi_tu_compile(tmp_path, {
        "a.c": "int g = 42;\n",
        "b.c": "char g;\nint main(void) { return 0; }\n",
    })
    assert not res.success
    assert any("incompatible" in e for e in res.errors)


def test_compatible_tentative_definitions(tmp_path):
    """Tentative definitions with same type should be fine."""
    res = _multi_tu_compile(tmp_path, {
        "a.c": "int g;\nvoid set(void) { g = 42; }\n",
        "b.c": "int g;\nvoid set(void);\nint main(void) { set(); return g == 42 ? 0 : 1; }\n",
    })
    assert res.success, f"Expected success: {res.errors}"
    p = subprocess.run([str(tmp_path / "out")], check=False, timeout=5)
    assert p.returncode == 0


def test_multiple_strong_definitions_rejected(tmp_path):
    """Two strong definitions of the same global should fail."""
    res = _multi_tu_compile(tmp_path, {
        "a.c": "int g = 1;\n",
        "b.c": "int g = 2;\nint main(void) { return 0; }\n",
    })
    assert not res.success
    assert any("multiple" in e for e in res.errors)
