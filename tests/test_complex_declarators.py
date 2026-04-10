"""Tests for complex nested declarator parsing (Requirements 16.1, 16.2)."""
from __future__ import annotations

from pathlib import Path

from pycc.compiler import Compiler


def _compile_and_run(tmp_path: Path, code: str) -> int:
    import subprocess

    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)

    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(out_path))
    assert res.success, "compile failed: " + "\n".join(res.errors)

    p = subprocess.run([str(out_path)], check=False)
    return p.returncode


def _compile_only(tmp_path: Path, code: str) -> bool:
    """Compile without linking/running — just check parsing + semantics."""
    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)

    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(out_path))
    return res.success


# ---------------------------------------------------------------------------
# Requirement 16.1: int (*(*fp)(int))[10] — pointer to function returning
# pointer to array of 10 ints
# ---------------------------------------------------------------------------

def test_nested_fnptr_returning_array_ptr_global_parse(tmp_path: Path):
    """Global declaration of int (*(*fp)(int))[10] should parse."""
    code = "int (*(*fp)(int))[10];\nint main(void){ return 0; }\n"
    assert _compile_only(tmp_path, code)


def test_nested_fnptr_returning_array_ptr_local_parse(tmp_path: Path):
    """Local declaration of int (*(*fp)(int))[10] should parse."""
    code = "int main(void){ int (*(*fp)(int))[10]; return 0; }\n"
    assert _compile_only(tmp_path, code)


# ---------------------------------------------------------------------------
# Requirement 16.2: int (*f(int))(double) — function returning function pointer
# ---------------------------------------------------------------------------

def test_function_returning_fnptr_parse(tmp_path: Path):
    """int (*f(int))(double) should parse as a function declaration."""
    code = "int (*f(int a))(double b);\nint main(void){ return 0; }\n"
    assert _compile_only(tmp_path, code)


def test_function_returning_fnptr_compile_and_run(tmp_path: Path):
    """Function returning function pointer — full compile + run."""
    code = r"""
int add1(double x) { return (int)x + 1; }

int (*get_fn(int sel))(double) {
    return add1;
}

int main(void) {
    int (*fp)(double);
    fp = get_fn(0);
    return fp(41.0) == 42 ? 0 : 1;
}
""".lstrip()
    assert _compile_and_run(tmp_path, code) == 0


# ---------------------------------------------------------------------------
# Additional complex declarator patterns
# ---------------------------------------------------------------------------

def test_pointer_to_array_global(tmp_path: Path):
    """int (*p)[10] at global scope should parse."""
    code = "int (*p)[10];\nint main(void){ return 0; }\n"
    assert _compile_only(tmp_path, code)


def test_pointer_to_pointer_paren_global(tmp_path: Path):
    """int (**pp) at global scope should parse."""
    code = "int (**pp);\nint main(void){ return 0; }\n"
    assert _compile_only(tmp_path, code)


def test_function_pointer_local_with_call(tmp_path: Path):
    """Basic function pointer at local scope — compile + run."""
    code = r"""
int inc(int x) { return x + 1; }
int main(void) {
    int (*fp)(int);
    fp = inc;
    return fp(41) == 42 ? 0 : 1;
}
""".lstrip()
    assert _compile_and_run(tmp_path, code) == 0
