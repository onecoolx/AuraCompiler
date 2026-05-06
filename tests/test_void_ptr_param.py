"""Tests for void* parameter handling.

Ensures void *p is not confused with (void) — zero-parameter marker.
"""
import subprocess
from pycc.compiler import Compiler


def _compile_and_run(tmp_path, code):
    c = tmp_path / "t.c"
    o = tmp_path / "t"
    c.write_text(code)
    res = Compiler(optimize=False).compile_file(str(c), str(o))
    assert res.success, "compile failed: " + "\n".join(res.errors)
    p = subprocess.run([str(o)], check=False, timeout=5)
    return p.returncode


def test_void_ptr_param_not_zero_params(tmp_path):
    """void gl_free(void *p) should have 1 parameter, not 0."""
    code = r"""
void my_free(void *p) { }
int main(void) {
    int x = 42;
    my_free(&x);
    return 0;
}
"""
    assert _compile_and_run(tmp_path, code) == 0


def test_void_ptr_param_call_with_arg(tmp_path):
    """Calling a function declared with void* param should accept 1 arg."""
    code = r"""
void process(void *data) { }
int main(void) {
    int arr[3] = {1, 2, 3};
    process(arr);
    return 0;
}
"""
    assert _compile_and_run(tmp_path, code) == 0


def test_void_no_param_rejects_arg(tmp_path):
    """Calling f(void) with an argument should be rejected."""
    c = tmp_path / "t.c"
    c.write_text("void f(void) { }\nint main(void) { f(1); return 0; }\n")
    res = Compiler(optimize=False).compile_file(str(c), str(tmp_path / "t"))
    assert not res.success
    assert any("incorrect number" in e for e in res.errors)


def test_error_has_line_number(tmp_path):
    """Argument count error should include line number."""
    c = tmp_path / "t.c"
    c.write_text("void f(void) { }\nint main(void) { f(1); return 0; }\n")
    res = Compiler(optimize=False).compile_file(str(c), str(tmp_path / "t"))
    assert not res.success
    # GCC-compatible format: <file>:<line>:<col>: error: ...
    assert any("t.c:" in e and "error:" in e for e in res.errors)
