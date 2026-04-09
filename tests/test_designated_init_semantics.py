"""Tests for designated initializer semantic validation (Task 3.2).

Validates that the semantic analyzer correctly:
- Rejects invalid struct member names in designators
- Rejects out-of-bounds array indices in designators
- Accepts valid designated initializers without errors
- Reports clear error messages

Requirements: 5.4, 5.6
"""

import pytest
from pycc.lexer import Lexer
from pycc.parser import Parser
from pycc.semantics import SemanticAnalyzer, SemanticError


def _analyze(code: str):
    """Lex, parse, and run semantic analysis. Returns SemanticContext."""
    tokens = Lexer(code).tokenize()
    ast = Parser(tokens).parse()
    sa = SemanticAnalyzer()
    return sa.analyze(ast)


def _analyze_errors(code: str) -> list:
    """Lex, parse, and run semantic analysis. Returns list of error strings."""
    tokens = Lexer(code).tokenize()
    ast = Parser(tokens).parse()
    sa = SemanticAnalyzer()
    try:
        sa.analyze(ast)
        return []
    except SemanticError as e:
        return str(e).split("\n")


# ── Valid designated initializers (should pass without errors) ──────

def test_valid_struct_member_designator():
    """Valid .member designators should not produce errors."""
    code = """
struct S { int x; int y; };
int main() {
    struct S s = { .x = 1, .y = 2 };
    return 0;
}
"""
    _analyze(code)  # Should not raise


def test_valid_array_index_designator():
    """Valid [index] designators within bounds should not produce errors."""
    code = """
int main() {
    int a[4] = { [0] = 10, [3] = 40 };
    return 0;
}
"""
    _analyze(code)  # Should not raise


def test_valid_mixed_designated_and_sequential():
    """Mixed designated and non-designated elements should pass."""
    code = """
struct S { int a; int b; int c; };
int main() {
    struct S s = { 1, .c = 3 };
    return 0;
}
"""
    _analyze(code)  # Should not raise


# ── Invalid struct member name ─────────────────────────────────────

def test_invalid_struct_member_name():
    """Designator with non-existent member name should produce an error."""
    code = """
struct S { int x; int y; };
int main() {
    struct S s = { .z = 1 };
    return 0;
}
"""
    errors = _analyze_errors(code)
    assert any("has no member named 'z'" in e for e in errors), \
        f"Expected error about non-existent member 'z', got: {errors}"


def test_invalid_struct_member_name_global():
    """Designator with non-existent member name at global scope."""
    code = """
struct S { int x; int y; };
struct S g = { .nonexistent = 42 };
"""
    errors = _analyze_errors(code)
    assert any("has no member named 'nonexistent'" in e for e in errors), \
        f"Expected error about non-existent member, got: {errors}"


# ── Array index out of bounds ──────────────────────────────────────

def test_array_index_exceeds_size():
    """Array designator with index >= array size should produce an error."""
    code = """
int main() {
    int a[3] = { [3] = 99 };
    return 0;
}
"""
    errors = _analyze_errors(code)
    assert any("array index 3 exceeds array size 3" in e for e in errors), \
        f"Expected error about array index exceeding size, got: {errors}"


def test_array_index_negative():
    """Array designator with negative index should produce an error."""
    code = """
int main() {
    int a[5] = { [-1] = 99 };
    return 0;
}
"""
    errors = _analyze_errors(code)
    # The parser may represent -1 as UnaryOp('-', IntLiteral(1))
    # which _eval_const_int should handle
    assert any("negative" in e for e in errors), \
        f"Expected error about negative index, got: {errors}"


def test_array_large_index_out_of_bounds():
    """Array designator with large index should produce an error."""
    code = """
int main() {
    int a[2] = { [100] = 1 };
    return 0;
}
"""
    errors = _analyze_errors(code)
    assert any("array index 100 exceeds array size 2" in e for e in errors), \
        f"Expected error about array index exceeding size, got: {errors}"


# ── Nested designator validation ───────────────────────────────────

def test_nested_designator_invalid_inner_member():
    """Nested designator with invalid inner member should produce an error."""
    code = """
struct Inner { int m; };
struct Outer { struct Inner inner; };
int main() {
    struct Outer o = { .inner.bad = 42 };
    return 0;
}
"""
    errors = _analyze_errors(code)
    assert any("has no member named 'bad'" in e for e in errors), \
        f"Expected error about non-existent inner member, got: {errors}"


# ── Valid edge cases ───────────────────────────────────────────────

def test_valid_array_index_at_boundary():
    """Array designator at last valid index should pass."""
    code = """
int main() {
    int a[5] = { [4] = 99 };
    return 0;
}
"""
    _analyze(code)  # Should not raise


def test_valid_array_index_zero():
    """Array designator at index 0 should pass."""
    code = """
int main() {
    int a[1] = { [0] = 42 };
    return 0;
}
"""
    _analyze(code)  # Should not raise


def test_plain_initializer_still_works():
    """Non-designated initializers should still pass semantic analysis."""
    code = """
struct S { int x; int y; };
int main() {
    struct S s = { 1, 2 };
    return 0;
}
"""
    _analyze(code)  # Should not raise
