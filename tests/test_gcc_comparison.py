"""Correctness comparison tests: pycc vs gcc -std=c89.

Each test compiles the same C89 program with both pycc and gcc, runs both
executables, and asserts they produce the same exit code.

Requires: gcc installed on the system (skips if not available).
"""
import os
import subprocess
import shutil

import pytest

from pycc.compiler import Compiler

_GCC = shutil.which("gcc")
pytestmark = pytest.mark.skipif(_GCC is None, reason="gcc not found")


def _run(exe, timeout=5):
    """Run an executable and return its exit code."""
    p = subprocess.run([str(exe)], check=False, timeout=timeout,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return p.returncode


def _gcc_compile(src, out, extra_flags=None):
    """Compile with gcc -std=c89 -pedantic."""
    cmd = [_GCC, "-std=c89", "-pedantic", "-w", "-o", str(out), str(src)]
    if extra_flags:
        cmd.extend(extra_flags)
    r = subprocess.run(cmd, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return r.returncode == 0


def _pycc_compile(src, out):
    """Compile with pycc."""
    comp = Compiler(optimize=False)
    res = comp.compile_file(str(src), str(out))
    return res.success


def _compare(tmp_path, code, name="test"):
    """Compile with both compilers, run both, assert same exit code."""
    src = tmp_path / f"{name}.c"
    src.write_text(code)

    gcc_out = tmp_path / f"{name}_gcc"
    pycc_out = tmp_path / f"{name}_pycc"

    assert _gcc_compile(src, gcc_out), f"gcc failed to compile {name}"
    assert _pycc_compile(src, pycc_out), f"pycc failed to compile {name}"

    gcc_rc = _run(gcc_out)
    pycc_rc = _run(pycc_out)

    assert pycc_rc == gcc_rc, (
        f"Exit code mismatch for {name}: gcc={gcc_rc}, pycc={pycc_rc}\n"
        f"Source:\n{code}"
    )
    return pycc_rc


# ── Arithmetic ────────────────────────────────────────────────────────

def test_integer_arithmetic(tmp_path):
    _compare(tmp_path, r"""
int main(void) {
    int a = 10, b = 3;
    int sum = a + b;
    int diff = a - b;
    int prod = a * b;
    int quot = a / b;
    int rem = a % b;
    return (sum == 13 && diff == 7 && prod == 30 && quot == 3 && rem == 1) ? 0 : 1;
}
""")


def test_unsigned_arithmetic(tmp_path):
    _compare(tmp_path, r"""
int main(void) {
    unsigned int a = 4294967295u;
    unsigned int b = a + 1;
    return b == 0 ? 0 : 1;
}
""")


def test_bitwise_ops(tmp_path):
    _compare(tmp_path, r"""
int main(void) {
    int a = 0xFF;
    int b = 0x0F;
    return ((a & b) == 0x0F && (a | b) == 0xFF && (a ^ b) == 0xF0) ? 0 : 1;
}
""")


def test_shift_ops(tmp_path):
    _compare(tmp_path, r"""
int main(void) {
    int a = 1;
    return (a << 4) == 16 && (16 >> 2) == 4 ? 0 : 1;
}
""")


# ── Control flow ──────────────────────────────────────────────────────

def test_if_else(tmp_path):
    _compare(tmp_path, r"""
int main(void) {
    int x = 10;
    if (x > 5) return 0;
    else return 1;
}
""")


def test_for_loop(tmp_path):
    _compare(tmp_path, r"""
int main(void) {
    int sum = 0;
    int i;
    for (i = 1; i <= 10; i++) sum += i;
    return sum == 55 ? 0 : 1;
}
""")


def test_while_loop(tmp_path):
    _compare(tmp_path, r"""
int main(void) {
    int n = 10, sum = 0;
    while (n > 0) { sum += n; n--; }
    return sum == 55 ? 0 : 1;
}
""")


def test_do_while(tmp_path):
    _compare(tmp_path, r"""
int main(void) {
    int i = 0;
    do { i++; } while (i < 5);
    return i == 5 ? 0 : 1;
}
""")


def test_switch_case(tmp_path):
    _compare(tmp_path, r"""
int main(void) {
    int x = 2;
    int r;
    switch (x) {
        case 1: r = 10; break;
        case 2: r = 20; break;
        case 3: r = 30; break;
        default: r = 0; break;
    }
    return r == 20 ? 0 : 1;
}
""")


def test_switch_fallthrough(tmp_path):
    _compare(tmp_path, r"""
int main(void) {
    int x = 1, r = 0;
    switch (x) {
        case 1: r += 1;
        case 2: r += 2;
        case 3: r += 3; break;
        default: r = 99;
    }
    return r == 6 ? 0 : 1;
}
""")


def test_goto(tmp_path):
    _compare(tmp_path, r"""
int main(void) {
    int x = 0;
    goto skip;
    x = 99;
skip:
    return x == 0 ? 0 : 1;
}
""")


def test_nested_loops_break_continue(tmp_path):
    _compare(tmp_path, r"""
int main(void) {
    int sum = 0;
    int i, j;
    for (i = 0; i < 5; i++) {
        if (i == 3) continue;
        for (j = 0; j < 3; j++) {
            if (j == 2) break;
            sum++;
        }
    }
    return sum == 8 ? 0 : 1;
}
""")


# ── Functions ─────────────────────────────────────────────────────────

def test_recursive_factorial(tmp_path):
    _compare(tmp_path, r"""
int fact(int n) {
    if (n <= 1) return 1;
    return n * fact(n - 1);
}
int main(void) {
    return fact(6) == 720 ? 0 : 1;
}
""")


def test_function_pointer(tmp_path):
    _compare(tmp_path, r"""
int add(int a, int b) { return a + b; }
int sub(int a, int b) { return a - b; }
int apply(int (*f)(int, int), int x, int y) { return f(x, y); }
int main(void) {
    return (apply(add, 3, 4) == 7 && apply(sub, 10, 3) == 7) ? 0 : 1;
}
""")


# ── Structs ───────────────────────────────────────────────────────────

def test_struct_by_value(tmp_path):
    _compare(tmp_path, r"""
struct Point { int x; int y; };
struct Point make(int a, int b) {
    struct Point p;
    p.x = a;
    p.y = b;
    return p;
}
int main(void) {
    struct Point p = make(10, 20);
    struct Point q;
    q = p;
    return (q.x + q.y) == 30 ? 0 : 1;
}
""")


def test_struct_linked_list(tmp_path):
    _compare(tmp_path, r"""
struct Node { int val; struct Node *next; };
int sum(struct Node *h) {
    int t = 0;
    while (h) { t += h->val; h = h->next; }
    return t;
}
int main(void) {
    struct Node c; c.val = 3; c.next = 0;
    struct Node b; b.val = 2; b.next = &c;
    struct Node a; a.val = 1; a.next = &b;
    return sum(&a) == 6 ? 0 : 1;
}
""")


def test_nested_struct(tmp_path):
    _compare(tmp_path, r"""
struct Inner { int a; int b; };
struct Outer { struct Inner in; int c; };
int main(void) {
    struct Outer o;
    o.in.a = 1; o.in.b = 2; o.c = 3;
    return (o.in.a + o.in.b + o.c) == 6 ? 0 : 1;
}
""")


# ── Arrays ────────────────────────────────────────────────────────────

def test_array_sum(tmp_path):
    _compare(tmp_path, r"""
int main(void) {
    int a[5] = {1, 2, 3, 4, 5};
    int sum = 0;
    int i;
    for (i = 0; i < 5; i++) sum += a[i];
    return sum == 15 ? 0 : 1;
}
""")


def test_string_length(tmp_path):
    _compare(tmp_path, r"""
int main(void) {
    char s[] = "hello";
    int len = 0;
    char *p = s;
    while (*p) { len++; p++; }
    return len == 5 ? 0 : 1;
}
""")


@pytest.mark.skip(reason="2D array brace-enclosed initializer not yet supported")
def test_2d_array(tmp_path):
    _compare(tmp_path, r"""
int main(void) {
    int m[2][3] = {{1,2,3},{4,5,6}};
    int sum = 0;
    int i, j;
    for (i = 0; i < 2; i++)
        for (j = 0; j < 3; j++)
            sum += m[i][j];
    return sum == 21 ? 0 : 1;
}
""")


# ── Pointers ──────────────────────────────────────────────────────────

def test_pointer_arithmetic(tmp_path):
    _compare(tmp_path, r"""
int main(void) {
    int a[5] = {10, 20, 30, 40, 50};
    int *p = a;
    return *(p + 3) == 40 ? 0 : 1;
}
""")


def test_pointer_to_pointer(tmp_path):
    _compare(tmp_path, r"""
int main(void) {
    int x = 42;
    int *p = &x;
    int **pp = &p;
    return **pp == 42 ? 0 : 1;
}
""")


# ── Enum ──────────────────────────────────────────────────────────────

def test_enum_values(tmp_path):
    _compare(tmp_path, r"""
enum Color { RED, GREEN = 5, BLUE };
int main(void) {
    return (RED == 0 && GREEN == 5 && BLUE == 6) ? 0 : 1;
}
""")


# ── Typedef ───────────────────────────────────────────────────────────

def test_typedef(tmp_path):
    _compare(tmp_path, r"""
typedef int myint;
typedef struct { int x; int y; } Point;
int main(void) {
    myint a = 42;
    Point p;
    p.x = 10;
    p.y = 20;
    return (a == 42 && p.x + p.y == 30) ? 0 : 1;
}
""")


# ── Cast ──────────────────────────────────────────────────────────────

def test_int_float_cast(tmp_path):
    _compare(tmp_path, r"""
int main(void) {
    double d = 3.7;
    int i = (int)d;
    double d2 = (double)i;
    return (i == 3) ? 0 : 1;
}
""")


# ── Sizeof ────────────────────────────────────────────────────────────

def test_sizeof_types(tmp_path):
    _compare(tmp_path, r"""
int main(void) {
    return (sizeof(char) == 1 && sizeof(int) == 4 && sizeof(long) == 8) ? 0 : 1;
}
""")


def test_sizeof_struct(tmp_path):
    _compare(tmp_path, r"""
struct S { char c; int i; };
int main(void) {
    return sizeof(struct S) == 8 ? 0 : 1;
}
""")


# ── Ternary ───────────────────────────────────────────────────────────

def test_ternary(tmp_path):
    _compare(tmp_path, r"""
int main(void) {
    int a = 5, b = 10;
    int max = (a > b) ? a : b;
    return max == 10 ? 0 : 1;
}
""")


# ── Comma operator ────────────────────────────────────────────────────

def test_comma_operator(tmp_path):
    _compare(tmp_path, r"""
int main(void) {
    int a = (1, 2, 3);
    return a == 3 ? 0 : 1;
}
""")


# ── Short circuit ─────────────────────────────────────────────────────

def test_short_circuit(tmp_path):
    _compare(tmp_path, r"""
int side = 0;
int f(void) { side = 1; return 1; }
int main(void) {
    int r = (0 && f());
    return (r == 0 && side == 0) ? 0 : 1;
}
""")


# ── Designated initializers ──────────────────────────────────────────

def test_designated_init_struct(tmp_path):
    _compare(tmp_path, r"""
struct S { int a; int b; int c; };
int main(void) {
    struct S s = { .c = 30, .a = 10 };
    return (s.a == 10 && s.b == 0 && s.c == 30) ? 0 : 1;
}
""")


def test_designated_init_array(tmp_path):
    _compare(tmp_path, r"""
int main(void) {
    int a[5] = { [3] = 42 };
    return (a[0] == 0 && a[3] == 42 && a[4] == 0) ? 0 : 1;
}
""")


# ── Volatile ──────────────────────────────────────────────────────────

def test_volatile_basic(tmp_path):
    _compare(tmp_path, r"""
int main(void) {
    volatile int x = 0;
    x = 42;
    return x == 42 ? 0 : 1;
}
""")


# ── Union ─────────────────────────────────────────────────────────────

def test_union_basic(tmp_path):
    _compare(tmp_path, r"""
union U { int i; char c; };
int main(void) {
    union U u;
    u.i = 65;
    return u.c == 65 ? 0 : 1;
}
""")
