"""Tests for goto label uniqueness across functions."""
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


def test_same_label_name_in_two_functions(tmp_path):
    """Two functions with the same label name should not conflict."""
    code = r"""
int f(int x) {
    if (x > 0) goto done;
    return -1;
done:
    return x;
}
int g(int x) {
    if (x > 0) goto done;
    return -2;
done:
    return x * 2;
}
int main(void) {
    return (f(5) == 5 && g(3) == 6) ? 0 : 1;
}
"""
    assert _compile_and_run(tmp_path, code) == 0


def test_error_label_in_two_functions(tmp_path):
    """Two functions with 'error:' label should not conflict."""
    code = r"""
int validate_a(int x) {
    if (x < 0) goto error;
    return 1;
error:
    return 0;
}
int validate_b(int x) {
    if (x > 100) goto error;
    return 1;
error:
    return 0;
}
int main(void) {
    return (validate_a(5) == 1 && validate_b(50) == 1) ? 0 : 1;
}
"""
    assert _compile_and_run(tmp_path, code) == 0
