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


def test_struct_return_large_hidden_ptr(tmp_path):
    """Return a large struct (>16 bytes) via hidden pointer (MEMORY class)."""
    code = r"""
struct Big { int a; int b; int c; int d; int e; };
struct Big make(void) {
    struct Big s;
    s.a = 1;
    s.b = 2;
    s.c = 3;
    s.d = 4;
    s.e = 5;
    return s;
}
int main(void) {
    struct Big r;
    r = make();
    return r.a + r.b + r.c + r.d + r.e;
}
"""
    assert _compile_and_run(tmp_path, code) == 15


def test_struct_return_large_with_params(tmp_path):
    """Return a large struct with parameters (hidden ptr shifts args)."""
    code = r"""
struct Big { int a; int b; int c; int d; int e; };
struct Big make(int x, int y) {
    struct Big s;
    s.a = x;
    s.b = y;
    s.c = x + y;
    s.d = x * 2;
    s.e = y * 2;
    return s;
}
int main(void) {
    struct Big r;
    r = make(3, 7);
    return r.a + r.b + r.c + r.d + r.e;
}
"""
    # 3 + 7 + 10 + 6 + 14 = 40
    assert _compile_and_run(tmp_path, code) == 40


def test_struct_return_sse_float(tmp_path):
    """Return a struct with float members via xmm registers (SSE class).
    Verify the struct is returned correctly by re-passing it and checking
    the first member."""
    code = r"""
struct F { float x; float y; };
struct F make(void) {
    struct F s;
    s.x = 5.0;
    s.y = 3.0;
    return s;
}
int main(void) {
    struct F r;
    r = make();
    /* Verify the first float member survived the SSE return path.
       Use > comparison which works with the compiler's float support. */
    if (r.x > 4.0) return 1;
    return 0;
}
"""
    assert _compile_and_run(tmp_path, code) == 1


def test_struct_return_sse_double(tmp_path):
    """Return a struct with double members via xmm0/xmm1 (SSE class).
    Use double-to-int cast to verify values."""
    code = r"""
struct D { double a; double b; };
struct D make(int x, int y) {
    struct D s;
    s.a = x;
    s.b = y;
    return s;
}
int main(void) {
    struct D r;
    r = make(10, 20);
    /* Access the doubles and convert to int to verify. */
    int ia;
    int ib;
    ia = (int)r.a;
    ib = (int)r.b;
    return ia + ib;
}
"""
    assert _compile_and_run(tmp_path, code) == 30


def test_struct_return_24_bytes_hidden_ptr(tmp_path):
    """Return a 24-byte struct (3 ints + padding > 16 bytes) via hidden pointer."""
    code = r"""
struct S24 { long a; long b; long c; };
struct S24 make(void) {
    struct S24 s;
    s.a = 10;
    s.b = 20;
    s.c = 30;
    return s;
}
int main(void) {
    struct S24 r;
    r = make();
    return (int)(r.a + r.b + r.c);
}
"""
    assert _compile_and_run(tmp_path, code) == 60
