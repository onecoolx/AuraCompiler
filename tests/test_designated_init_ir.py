"""End-to-end tests for designated initializer IR generation (Tasks 3.3, 3.5).

These tests compile and run C code with designated initializers to verify
that the IR generator correctly lowers them to assignment sequences.

Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6
"""

import subprocess
from pycc.compiler import Compiler


def _compile_and_run(tmp_path, code: str) -> int:
    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)

    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(out_path))
    assert res.success, "compile failed: " + "\n".join(res.errors)

    p = subprocess.run([str(out_path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return p.returncode


def _compile_should_fail(tmp_path, code: str) -> bool:
    """Compile C code with pycc and return True if compilation fails."""
    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)

    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(out_path))
    return not res.success


# ── Struct member designators (.member = val) ──────────────────────

def test_struct_member_designator_basic(tmp_path):
    """Req 5.1: .member = val initializes the correct struct member."""
    code = r"""
struct S { int x; int y; };
int main() {
    struct S s = { .x = 10, .y = 20 };
    return (s.x == 10 && s.y == 20) ? 0 : 1;
}
"""
    assert _compile_and_run(tmp_path, code) == 0


def test_struct_member_designator_out_of_order(tmp_path):
    """Req 5.1: designators can specify members in any order."""
    code = r"""
struct S { int a; int b; int c; };
int main() {
    struct S s = { .c = 30, .a = 10, .b = 20 };
    return (s.a == 10 && s.b == 20 && s.c == 30) ? 0 : 1;
}
"""
    assert _compile_and_run(tmp_path, code) == 0


def test_struct_member_designator_partial(tmp_path):
    """Req 5.3: unspecified members are zero-filled."""
    code = r"""
struct S { int x; int y; int z; };
int main() {
    struct S s = { .y = 42 };
    return (s.x == 0 && s.y == 42 && s.z == 0) ? 0 : 1;
}
"""
    assert _compile_and_run(tmp_path, code) == 0


# ── Array index designators ([index] = val) ────────────────────────

def test_array_index_designator_basic(tmp_path):
    """Req 5.2: [index] = val initializes the correct array element."""
    code = r"""
int main() {
    int a[4] = { [0] = 10, [2] = 30 };
    return (a[0] == 10 && a[1] == 0 && a[2] == 30 && a[3] == 0) ? 0 : 1;
}
"""
    assert _compile_and_run(tmp_path, code) == 0


def test_array_index_designator_out_of_order(tmp_path):
    """Req 5.2: array designators can specify indices in any order."""
    code = r"""
int main() {
    int a[3] = { [2] = 3, [0] = 1, [1] = 2 };
    return (a[0] == 1 && a[1] == 2 && a[2] == 3) ? 0 : 1;
}
"""
    assert _compile_and_run(tmp_path, code) == 0


def test_array_index_designator_zero_fill(tmp_path):
    """Req 5.3: unspecified array elements are zero-filled."""
    code = r"""
int main() {
    int a[5] = { [4] = 99 };
    return (a[0] == 0 && a[1] == 0 && a[2] == 0 && a[3] == 0 && a[4] == 99) ? 0 : 1;
}
"""
    assert _compile_and_run(tmp_path, code) == 0


# ── Mixed designated and sequential ────────────────────────────────

def test_mixed_struct_designated_and_sequential(tmp_path):
    """Req 5.4: mixing designated and non-designated elements."""
    code = r"""
struct S { int a; int b; int c; };
int main() {
    struct S s = { 1, .c = 3 };
    return (s.a == 1 && s.b == 0 && s.c == 3) ? 0 : 1;
}
"""
    assert _compile_and_run(tmp_path, code) == 0


def test_mixed_array_designated_and_sequential(tmp_path):
    """Req 5.4: mixing designated and non-designated array elements."""
    code = r"""
int main() {
    int a[4] = { [2] = 20, 30 };
    return (a[0] == 0 && a[1] == 0 && a[2] == 20 && a[3] == 30) ? 0 : 1;
}
"""
    assert _compile_and_run(tmp_path, code) == 0


# ── Nested struct designators ──────────────────────────────────────

def test_nested_struct_designator(tmp_path):
    """Req 5.5: .inner.member = val for nested structs."""
    code = r"""
struct Inner { int m; int n; };
struct Outer { struct Inner inner; int z; };
int main() {
    struct Outer o = { .inner.m = 42, .z = 99 };
    return (o.inner.m == 42 && o.inner.n == 0 && o.z == 99) ? 0 : 1;
}
"""
    assert _compile_and_run(tmp_path, code) == 0


def test_nested_struct_brace_init(tmp_path):
    """Req 5.5: designated init with nested brace-enclosed initializer."""
    code = r"""
struct Inner { int a; int b; };
struct Outer { struct Inner inner; int c; };
int main() {
    struct Outer o = { .inner = {10, 20}, .c = 30 };
    return (o.inner.a == 10 && o.inner.b == 20 && o.c == 30) ? 0 : 1;
}
"""
    assert _compile_and_run(tmp_path, code) == 0


# ── Global designated initializers ─────────────────────────────────

def test_global_struct_designated_init(tmp_path):
    """Req 5.1: global struct with designated initializers."""
    code = r"""
struct S { int x; int y; int z; };
struct S g = { .y = 42 };
int main() {
    return (g.x == 0 && g.y == 42 && g.z == 0) ? 0 : 1;
}
"""
    assert _compile_and_run(tmp_path, code) == 0


def test_global_array_designated_init(tmp_path):
    """Req 5.2: global array with designated initializers."""
    code = r"""
int g[4] = { [1] = 10, [3] = 30 };
int main() {
    return (g[0] == 0 && g[1] == 10 && g[2] == 0 && g[3] == 30) ? 0 : 1;
}
"""
    assert _compile_and_run(tmp_path, code) == 0


# ── Edge cases: struct designators ─────────────────────────────────

def test_struct_single_member_designator(tmp_path):
    """Req 5.1: struct with only one member, designated."""
    code = r"""
struct S { int x; };
int main() {
    struct S s = { .x = 77 };
    return (s.x == 77) ? 0 : 1;
}
"""
    assert _compile_and_run(tmp_path, code) == 0


def test_struct_char_member_designator(tmp_path):
    """Req 5.1: struct with char members using designated init."""
    code = r"""
struct S { char a; int b; char c; };
int main() {
    struct S s = { .a = 65, .b = 100, .c = 66 };
    return (s.a == 65 && s.b == 100 && s.c == 66) ? 0 : 1;
}
"""
    assert _compile_and_run(tmp_path, code) == 0


def test_struct_all_members_designated(tmp_path):
    """Req 5.1: every member explicitly designated, no zero-fill needed."""
    code = r"""
struct S { int a; int b; int c; int d; };
int main() {
    struct S s = { .a = 1, .b = 2, .c = 3, .d = 4 };
    return (s.a == 1 && s.b == 2 && s.c == 3 && s.d == 4) ? 0 : 1;
}
"""
    assert _compile_and_run(tmp_path, code) == 0


def test_struct_designator_large_values(tmp_path):
    """Req 5.1: designated init with large int values."""
    code = r"""
struct S { int x; int y; };
int main() {
    struct S s = { .x = 2147483647, .y = 0 };
    return (s.x == 2147483647 && s.y == 0) ? 0 : 1;
}
"""
    assert _compile_and_run(tmp_path, code) == 0


def test_struct_duplicate_designator_last_wins(tmp_path):
    """Req 5.1: duplicate designator for same member — last value wins."""
    code = r"""
struct S { int x; int y; };
int main() {
    struct S s = { .x = 1, .x = 99 };
    return (s.x == 99 && s.y == 0) ? 0 : 1;
}
"""
    assert _compile_and_run(tmp_path, code) == 0


# ── Edge cases: array designators ──────────────────────────────────

def test_array_single_element_designator(tmp_path):
    """Req 5.2: array of size 1 with designated init."""
    code = r"""
int main() {
    int a[1] = { [0] = 42 };
    return (a[0] == 42) ? 0 : 1;
}
"""
    assert _compile_and_run(tmp_path, code) == 0


def test_array_designator_large_value(tmp_path):
    """Req 5.2: array designated init with large values."""
    code = r"""
int main() {
    int a[3] = { [0] = 1000000, [2] = 999 };
    return (a[0] == 1000000 && a[1] == 0 && a[2] == 999) ? 0 : 1;
}
"""
    assert _compile_and_run(tmp_path, code) == 0


def test_array_all_elements_designated(tmp_path):
    """Req 5.2: every element explicitly designated."""
    code = r"""
int main() {
    int a[3] = { [0] = 10, [1] = 20, [2] = 30 };
    return (a[0] == 10 && a[1] == 20 && a[2] == 30) ? 0 : 1;
}
"""
    assert _compile_and_run(tmp_path, code) == 0


def test_array_duplicate_designator_last_wins(tmp_path):
    """Req 5.2: duplicate designator for same index — last value wins."""
    code = r"""
int main() {
    int a[3] = { [1] = 10, [1] = 77 };
    return (a[0] == 0 && a[1] == 77 && a[2] == 0) ? 0 : 1;
}
"""
    assert _compile_and_run(tmp_path, code) == 0


# ── Edge cases: mixed designated + sequential ──────────────────────

def test_mixed_sequential_then_designated_then_sequential(tmp_path):
    """Req 5.4: sequential, then designated, then sequential continuation."""
    code = r"""
struct S { int a; int b; int c; int d; };
int main() {
    struct S s = { 1, .c = 30, 40 };
    return (s.a == 1 && s.b == 0 && s.c == 30 && s.d == 40) ? 0 : 1;
}
"""
    assert _compile_and_run(tmp_path, code) == 0


def test_mixed_array_sequential_after_designator(tmp_path):
    """Req 5.4: array sequential element continues after designated index."""
    code = r"""
int main() {
    int a[5] = { 1, [3] = 30, 40 };
    return (a[0] == 1 && a[1] == 0 && a[2] == 0 && a[3] == 30 && a[4] == 40) ? 0 : 1;
}
"""
    assert _compile_and_run(tmp_path, code) == 0


# ── Edge cases: nested designators ─────────────────────────────────

def test_nested_designator_all_inner_members(tmp_path):
    """Req 5.5: nested designator setting all inner struct members."""
    code = r"""
struct Inner { int a; int b; };
struct Outer { struct Inner inner; int c; };
int main() {
    struct Outer o = { .inner.a = 10, .inner.b = 20, .c = 30 };
    return (o.inner.a == 10 && o.inner.b == 20 && o.c == 30) ? 0 : 1;
}
"""
    assert _compile_and_run(tmp_path, code) == 0


def test_nested_designator_zero_fill_inner(tmp_path):
    """Req 5.3, 5.5: nested designator with partial inner init, rest zero-filled."""
    code = r"""
struct Inner { int x; int y; int z; };
struct Outer { struct Inner inner; int w; };
int main() {
    struct Outer o = { .inner.y = 42 };
    return (o.inner.x == 0 && o.inner.y == 42 && o.inner.z == 0 && o.w == 0) ? 0 : 1;
}
"""
    assert _compile_and_run(tmp_path, code) == 0


# ── Edge cases: global designated initializers ─────────────────────

def test_global_mixed_array_designated_and_sequential(tmp_path):
    """Req 5.2, 5.4: global array with mixed designated and sequential."""
    code = r"""
int g[4] = { [2] = 20, 30 };
int main() {
    return (g[0] == 0 && g[1] == 0 && g[2] == 20 && g[3] == 30) ? 0 : 1;
}
"""
    assert _compile_and_run(tmp_path, code) == 0


def test_global_struct_all_members_designated(tmp_path):
    """Req 5.1: global struct with all members designated."""
    code = r"""
struct S { int a; int b; int c; };
struct S g = { .c = 3, .a = 1, .b = 2 };
int main() {
    return (g.a == 1 && g.b == 2 && g.c == 3) ? 0 : 1;
}
"""
    assert _compile_and_run(tmp_path, code) == 0


# ── Error reporting: invalid member name and OOB index ─────────────

def test_error_invalid_struct_member(tmp_path):
    """Req 5.6: invalid member name should cause compile error."""
    code = r"""
struct S { int x; int y; };
int main() {
    struct S s = { .z = 1 };
    return 0;
}
"""
    assert _compile_should_fail(tmp_path, code)


def test_error_array_index_out_of_bounds(tmp_path):
    """Req 5.6: array index >= size should cause compile error."""
    code = r"""
int main() {
    int a[3] = { [3] = 99 };
    return 0;
}
"""
    assert _compile_should_fail(tmp_path, code)


def test_error_array_large_index(tmp_path):
    """Req 5.6: very large array index should cause compile error."""
    code = r"""
int main() {
    int a[2] = { [100] = 1 };
    return 0;
}
"""
    assert _compile_should_fail(tmp_path, code)


def test_error_nested_invalid_inner_member(tmp_path):
    """Req 5.6: nested designator with invalid inner member should fail."""
    code = r"""
struct Inner { int m; };
struct Outer { struct Inner inner; };
int main() {
    struct Outer o = { .inner.bad = 42 };
    return 0;
}
"""
    assert _compile_should_fail(tmp_path, code)
