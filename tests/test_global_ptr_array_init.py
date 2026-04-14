"""Tests for global pointer array initializers and const expr evaluation.

Covers:
- char *arr[] = {"str1", "str2"} - string pointer array
- void (*fn_arr[])(T) = {f, g} - function pointer array
- int arr[] = {1+2, 3*4} - constant expression initializers
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


def _compile_only(tmp_path, code):
    c = tmp_path / "t.c"
    o = tmp_path / "t.o"
    c.write_text(code)
    res = Compiler(optimize=False).compile_file(str(c), str(o))
    return res.success, res.errors


def test_global_string_ptr_array(tmp_path):
    """char *arr[] = {"hello", "world"} should compile."""
    code = r"""
static char *greetings[] = {"hello", "world"};
int main(void) {
    return 0;
}
"""
    ok, errs = _compile_only(tmp_path, code)
    assert ok, "compile failed: " + "\n".join(errs)


def test_global_string_ptr_array_access(tmp_path):
    """Access element of a global string pointer array."""
    code = r"""
static char *names[] = {"alice", "bob"};
int main(void) {
    char *s = names[0];
    return s[0] == 'a' ? 0 : 1;
}
"""
    ok, errs = _compile_only(tmp_path, code)
    assert ok, "compile failed: " + "\n".join(errs)


def test_global_fnptr_array_compiles(tmp_path):
    """void (*table[])(int) = {f, g} should compile."""
    code = r"""
void f(int x) { }
void g(int x) { }
static void (*table[])(int) = { f, g };
int main(void) { return 0; }
"""
    ok, errs = _compile_only(tmp_path, code)
    assert ok, "compile failed: " + "\n".join(errs)


def test_global_int_array_const_expr(tmp_path):
    """int arr[] = {1+2, 3*4} with constant expressions should compile and run."""
    code = r"""
static int sizes[] = { 7 + 1, 4 + 1, 1 + 1, 3 + 1 };
int main(void) {
    return (sizes[0] == 8 && sizes[1] == 5 && sizes[2] == 2 && sizes[3] == 4) ? 0 : 1;
}
"""
    assert _compile_and_run(tmp_path, code) == 0


def test_global_int_array_complex_const_expr(tmp_path):
    """int arr[] = {2*3+1, 10/2} with complex constant expressions."""
    code = r"""
static int vals[] = { 2*3+1, 10/2, 1<<3, 0xFF & 0x0F };
int main(void) {
    return (vals[0] == 7 && vals[1] == 5 && vals[2] == 8 && vals[3] == 15) ? 0 : 1;
}
"""
    assert _compile_and_run(tmp_path, code) == 0
