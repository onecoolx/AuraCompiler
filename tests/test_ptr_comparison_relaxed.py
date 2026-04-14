"""Tests for relaxed pointer comparison semantics.

C89 allows pointer == 0, pointer == pointer (even through member access),
and should not reject comparisons when the type of one side is unknown.
"""
from pycc.compiler import Compiler


def _compile_ok(tmp_path, code):
    c = tmp_path / "t.c"
    c.write_text(code)
    res = Compiler(optimize=False).compile_file(str(c), str(tmp_path / "t"))
    return res.success, res.errors


def test_ptr_eq_zero(tmp_path):
    """pointer == 0 should be allowed."""
    ok, _ = _compile_ok(tmp_path, "int main(void) { int *p = 0; return p == 0 ? 0 : 1; }\n")
    assert ok


def test_ptr_ne_zero(tmp_path):
    """pointer != 0 should be allowed."""
    ok, _ = _compile_ok(tmp_path, "int main(void) { int *p = 0; return p != 0 ? 1 : 0; }\n")
    assert ok


def test_ptr_eq_member_access(tmp_path):
    """pointer == struct->member should be allowed."""
    code = r"""
struct S { int *p; };
int main(void) {
    int x = 42;
    struct S s;
    s.p = &x;
    int *q = &x;
    return q == s.p ? 0 : 1;
}
"""
    ok, errs = _compile_ok(tmp_path, code)
    assert ok, "compile failed: " + "\n".join(errs)


def test_ptr_eq_arrow_member(tmp_path):
    """pointer == ptr->member should be allowed."""
    code = r"""
struct Node { int val; struct Node *next; };
int main(void) {
    struct Node a;
    a.val = 1;
    a.next = 0;
    struct Node *p = &a;
    struct Node *target = &a;
    return p == target ? 0 : 1;
}
"""
    ok, errs = _compile_ok(tmp_path, code)
    assert ok, "compile failed: " + "\n".join(errs)


def test_reject_ptr_eq_nonzero_int(tmp_path):
    """pointer == 42 should still be rejected."""
    code = "int main(void) { int *p = 0; return p == 42; }\n"
    ok, errs = _compile_ok(tmp_path, code)
    assert not ok
    assert any("pointer" in e and "non-pointer" in e for e in errs)
