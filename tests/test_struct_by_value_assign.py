"""Tests for struct/union by-value assignment."""
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


def test_struct_assign_simple(tmp_path):
    """struct S b; b = a; copies all members."""
    code = r"""
struct S { int x; int y; };
int main(void) {
    struct S a;
    struct S b;
    a.x = 10;
    a.y = 20;
    b = a;
    return b.x + b.y;
}
"""
    assert _compile_and_run(tmp_path, code) == 30


def test_struct_assign_overwrite(tmp_path):
    """Assignment overwrites previous values."""
    code = r"""
struct S { int x; int y; };
int main(void) {
    struct S a;
    struct S b;
    a.x = 3;
    a.y = 4;
    b.x = 99;
    b.y = 99;
    b = a;
    return b.x * 10 + b.y;
}
"""
    assert _compile_and_run(tmp_path, code) == 34


def test_struct_assign_with_char_members(tmp_path):
    """Struct with mixed-size members copies correctly."""
    code = r"""
struct S { char c; int i; };
int main(void) {
    struct S a;
    struct S b;
    a.c = 5;
    a.i = 42;
    b = a;
    return b.c + b.i;
}
"""
    assert _compile_and_run(tmp_path, code) == 47


def test_union_assign(tmp_path):
    """Union by-value assignment."""
    code = r"""
union U { int i; char c; };
int main(void) {
    union U a;
    union U b;
    a.i = 77;
    b = a;
    return b.i;
}
"""
    assert _compile_and_run(tmp_path, code) == 77


def test_struct_assign_nested(tmp_path):
    """Nested struct by-value assignment."""
    code = r"""
struct Inner { int a; int b; };
struct Outer { struct Inner in; int c; };
int main(void) {
    struct Outer x;
    struct Outer y;
    x.in.a = 1;
    x.in.b = 2;
    x.c = 3;
    y = x;
    return y.in.a + y.in.b + y.c;
}
"""
    assert _compile_and_run(tmp_path, code) == 6


def test_struct_init_from_another(tmp_path):
    """struct S b = a; initialization from another struct."""
    code = r"""
struct S { int x; int y; };
int main(void) {
    struct S a;
    a.x = 11;
    a.y = 22;
    struct S b = a;
    return b.x + b.y;
}
"""
    # Note: this may require C99-style declaration-after-statement.
    # If parser doesn't support it, we test assignment form only.
    assert _compile_and_run(tmp_path, code) == 33
