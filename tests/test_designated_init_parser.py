"""Tests for designated initializer parsing (Task 3.1).

This task is ONLY about parsing — we verify that the parser produces
correct Designator AST nodes.  Semantics validation (3.2) and IR
generation (3.3) are separate tasks.
"""

from pycc.lexer import Lexer
from pycc.parser import Parser
from pycc.ast_nodes import (
    Designator,
    Initializer,
    IntLiteral,
    Declaration,
    FunctionDecl,
)


def _parse(code: str):
    """Lex + parse, return the AST Program node."""
    tokens = Lexer(code).tokenize()
    return Parser(tokens).parse()


def _get_init_elements(code: str):
    """Parse code containing a single local variable with an initializer
    and return the Initializer.elements list."""
    prog = _parse(code)
    # Walk into main -> body -> first Declaration with an initializer
    for decl in prog.declarations:
        if isinstance(decl, FunctionDecl) and decl.name == "main":
            body = decl.body
            for stmt in body.statements:
                # Statements in the body can be Declaration directly
                if isinstance(stmt, Declaration):
                    init = stmt.initializer
                    if isinstance(init, Initializer):
                        return init.elements
                # Or wrapped in DeclStmt
                d = getattr(stmt, "declaration", None)
                if d is not None:
                    init = getattr(d, "initializer", None)
                    if isinstance(init, Initializer):
                        return init.elements
    raise AssertionError("Could not find initializer in parsed AST")


# ── .member = val ──────────────────────────────────────────────────

def test_member_designator_basic():
    """Requirement 5.1: .member = val produces a Designator with member set."""
    code = """
struct S { int x; int y; };
int main() {
    struct S s = { .x = 1, .y = 2 };
    return 0;
}
"""
    elems = _get_init_elements(code)
    assert len(elems) == 2

    desig0, val0 = elems[0]
    assert isinstance(desig0, Designator)
    assert desig0.member == "x"
    assert desig0.index is None

    desig1, val1 = elems[1]
    assert isinstance(desig1, Designator)
    assert desig1.member == "y"
    assert desig1.index is None


# ── [index] = val ──────────────────────────────────────────────────

def test_array_designator_basic():
    """Requirement 5.2: [index] = val produces a Designator with index set."""
    code = """
int main() {
    int a[4] = { [0] = 10, [2] = 30 };
    return 0;
}
"""
    elems = _get_init_elements(code)
    assert len(elems) == 2

    desig0, _ = elems[0]
    assert isinstance(desig0, Designator)
    assert desig0.member is None
    assert isinstance(desig0.index, IntLiteral)
    assert desig0.index.value == 0

    desig1, _ = elems[1]
    assert isinstance(desig1, Designator)
    assert isinstance(desig1.index, IntLiteral)
    assert desig1.index.value == 2


# ── mixed designated + non-designated ──────────────────────────────

def test_mixed_designated_and_sequential():
    """Requirement 5.4: mixing designated and non-designated elements."""
    code = """
struct S { int a; int b; int c; };
int main() {
    struct S s = { 1, .c = 3, 2 };
    return 0;
}
"""
    elems = _get_init_elements(code)
    assert len(elems) == 3

    # First element: no designator
    assert elems[0][0] is None

    # Second element: .c designator
    assert isinstance(elems[1][0], Designator)
    assert elems[1][0].member == "c"

    # Third element: no designator
    assert elems[2][0] is None


# ── nested designators ─────────────────────────────────────────────

def test_nested_member_designator():
    """Requirement 5.5: .inner.member = val creates a chain of Designators."""
    code = """
struct Inner { int m; };
struct Outer { struct Inner inner; };
int main() {
    struct Outer o = { .inner.m = 42 };
    return 0;
}
"""
    elems = _get_init_elements(code)
    assert len(elems) == 1

    desig, _ = elems[0]
    assert isinstance(desig, Designator)
    assert desig.member == "inner"
    assert desig.next is not None
    assert isinstance(desig.next, Designator)
    assert desig.next.member == "m"
    assert desig.next.next is None


# ── non-designated initializer still works ─────────────────────────

def test_plain_initializer_unchanged():
    """Existing non-designated initializers must still parse correctly."""
    code = """
int main() {
    int a[3] = {1, 2, 3};
    return 0;
}
"""
    elems = _get_init_elements(code)
    assert len(elems) == 3
    for desig, val in elems:
        assert desig is None


# ── trailing comma with designator ─────────────────────────────────

def test_trailing_comma_with_designator():
    """Trailing comma after designated element should parse fine."""
    code = """
struct S { int x; };
int main() {
    struct S s = { .x = 1, };
    return 0;
}
"""
    elems = _get_init_elements(code)
    assert len(elems) == 1
    assert isinstance(elems[0][0], Designator)
    assert elems[0][0].member == "x"


# ── array designator with expression index ─────────────────────────

def test_array_designator_with_expression():
    """Array designator with a constant expression index."""
    code = """
int main() {
    int a[10] = { [2 + 1] = 99 };
    return 0;
}
"""
    elems = _get_init_elements(code)
    assert len(elems) == 1
    desig, _ = elems[0]
    assert isinstance(desig, Designator)
    assert desig.index is not None
    assert desig.member is None
