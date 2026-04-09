"""Tests for struct/union by-value return."""
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


def test_struct_return_small(tmp_path):
    """Return a small struct (8 bytes, fits in rax)."""
    code = r"""
struct S { int x; int y; };
struct S make(int a, int b) {
    struct S s;
    s.x = a;
    s.y = b;
    return s;
}
int main(void) {
    struct S r;
    r = make(10, 20);
    return r.x + r.y;
}
"""
    assert _compile_and_run(tmp_path, code) == 30


def test_struct_return_12_bytes(tmp_path):
    """Return a 12-byte struct (rax + rdx)."""
    code = r"""
struct S { int a; int b; int c; };
struct S make(void) {
    struct S s;
    s.a = 1;
    s.b = 2;
    s.c = 3;
    return s;
}
int main(void) {
    struct S r;
    r = make();
    return r.a + r.b + r.c;
}
"""
    assert _compile_and_run(tmp_path, code) == 6


def test_struct_return_and_use_member(tmp_path):
    """Return struct and immediately access a member."""
    code = r"""
struct Point { int x; int y; };
struct Point origin(void) {
    struct Point p;
    p.x = 0;
    p.y = 0;
    return p;
}
int main(void) {
    struct Point p;
    p = origin();
    return p.x + p.y;
}
"""
    assert _compile_and_run(tmp_path, code) == 0
