"""Test: const <typedef-name> *param is parsed correctly."""
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


def test_const_typedef_void_ptr_param(tmp_path):
    code = r"""
typedef void GLvoid;
void f(const GLvoid *pointer) { }
int main(void) { int x = 1; f(&x); return 0; }
"""
    assert _compile_and_run(tmp_path, code) == 0


def test_const_typedef_int_ptr_param(tmp_path):
    code = r"""
typedef int myint;
int sum(const myint *arr, int n) {
    int s = 0;
    int i;
    for (i = 0; i < n; i++) s = s + arr[i];
    return s;
}
int main(void) {
    int a[3] = {1, 2, 3};
    return sum(a, 3) == 6 ? 0 : 1;
}
"""
    assert _compile_and_run(tmp_path, code) == 0
