"""Unit tests for function pointer full type compatibility checks (Task 5.2).

Tests that the semantics module correctly checks parameter types and return
types when assigning function pointers, not just parameter count.

Requirements: 7.1, 7.2, 7.3
"""
from __future__ import annotations

from pathlib import Path

from pycc.compiler import Compiler


def _compile(tmp_path: Path, c_src: str):
    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(c_src)
    comp = Compiler(optimize=False)
    return comp.compile_file(str(c_path), str(out_path))


def _has_error(result, substring: str) -> bool:
    """Check if any error message contains the given substring."""
    for e in getattr(result, "errors", []):
        if substring in str(e):
            return True
    return False


# ---- Compatible assignments (should succeed) ----

def test_compatible_same_signature(tmp_path):
    """Same signature: int(int, int) -> int(int, int) should be compatible."""
    code = """
int add(int a, int b) { return a + b; }
int main(void) {
    int (*fp)(int, int) = add;
    return fp(1, 2);
}
""".lstrip()
    res = _compile(tmp_path, code)
    assert res.success, f"Expected success but got errors: {getattr(res, 'errors', [])}"


def test_compatible_void_return(tmp_path):
    """void(int) -> void(int) should be compatible."""
    code = """
void nop(int x) { }
int main(void) {
    void (*fp)(int) = nop;
    fp(42);
    return 0;
}
""".lstrip()
    res = _compile(tmp_path, code)
    assert res.success, f"Expected success but got errors: {getattr(res, 'errors', [])}"


def test_compatible_no_params(tmp_path):
    """int(void) -> int(void) should be compatible."""
    code = """
int zero(void) { return 0; }
int main(void) {
    int (*fp)(void) = zero;
    return fp();
}
""".lstrip()
    res = _compile(tmp_path, code)
    assert res.success, f"Expected success but got errors: {getattr(res, 'errors', [])}"


# ---- Incompatible: parameter type mismatch ----

def test_reject_param_type_mismatch_int_vs_char_ptr(tmp_path):
    """int(int) assigned to int(*)(char*) should be rejected (param 1 type mismatch)."""
    code = """
int f(int a) { return a; }
int main(void) {
    int (*fp)(char *) = f;
    return 0;
}
""".lstrip()
    res = _compile(tmp_path, code)
    assert not res.success, "Expected failure for param type mismatch"


def test_reject_param_type_mismatch_int_vs_double(tmp_path):
    """int(int) assigned to int(*)(double) should be rejected (param 1 type mismatch)."""
    code = """
int f(int a) { return a; }
int main(void) {
    int (*fp)(double) = f;
    return 0;
}
""".lstrip()
    res = _compile(tmp_path, code)
    assert not res.success, "Expected failure for param type mismatch"


def test_reject_param_type_mismatch_second_param(tmp_path):
    """int(int, int) assigned to int(*)(int, char) should be rejected (param 2 type mismatch)."""
    code = """
int f(int a, int b) { return a + b; }
int main(void) {
    int (*fp)(int, char) = f;
    return 0;
}
""".lstrip()
    res = _compile(tmp_path, code)
    assert not res.success, "Expected failure for param 2 type mismatch"


# ---- Incompatible: return type mismatch ----

def test_reject_return_type_mismatch(tmp_path):
    """void(int) assigned to int(*)(int) should be rejected (return type mismatch)."""
    code = """
void f(int a) { }
int main(void) {
    int (*fp)(int) = f;
    return 0;
}
""".lstrip()
    res = _compile(tmp_path, code)
    assert not res.success, "Expected failure for return type mismatch"


# ---- Incompatible: arity mismatch (existing behavior preserved) ----

def test_reject_arity_mismatch(tmp_path):
    """int(int, int) assigned to int(*)(int) should be rejected (arity mismatch)."""
    code = """
int f(int a, int b) { return a + b; }
int main(void) {
    int (*fp)(int) = f;
    return 0;
}
""".lstrip()
    res = _compile(tmp_path, code)
    assert not res.success, "Expected failure for arity mismatch"
