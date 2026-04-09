"""Tests for struct/union by-value parameter passing."""
import subprocess
from pycc.compiler import Compiler


def _compile_and_run(tmp_path, code: str) -> int:
    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)
    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(out_path))
    assert res.success, "compile failed: " + "\n".join(res.errors)
    p = subprocess.run([str(out_path)], check=False, timeout=5)
    return p.returncode


def test_struct_param_small(tmp_path):
    """Pass a small struct (fits in one register) by value."""
    code = r"""
struct S { int x; int y; };
int sum(struct S s) {
    return s.x + s.y;
}
int main(void) {
    struct S a;
    a.x = 10;
    a.y = 20;
    return sum(a);
}
"""
    assert _compile_and_run(tmp_path, code) == 30


def test_struct_param_three_members(tmp_path):
    """Pass a struct with 3 int members (12 bytes, 2 registers)."""
    code = r"""
struct S { int a; int b; int c; };
int sum(struct S s) {
    return s.a + s.b + s.c;
}
int main(void) {
    struct S v;
    v.a = 1;
    v.b = 2;
    v.c = 3;
    return sum(v);
}
"""
    assert _compile_and_run(tmp_path, code) == 6


def test_struct_param_does_not_modify_caller(tmp_path):
    """Modifying struct param in callee does not affect caller."""
    code = r"""
struct S { int x; };
int f(struct S s) {
    s.x = 99;
    return s.x;
}
int main(void) {
    struct S a;
    a.x = 5;
    f(a);
    return a.x;
}
"""
    assert _compile_and_run(tmp_path, code) == 5


def test_struct_param_with_other_args(tmp_path):
    """Struct param mixed with scalar args."""
    code = r"""
struct S { int x; int y; };
int f(int before, struct S s, int after) {
    return before + s.x + s.y + after;
}
int main(void) {
    struct S a;
    a.x = 10;
    a.y = 20;
    return f(1, a, 2);
}
"""
    assert _compile_and_run(tmp_path, code) == 33
