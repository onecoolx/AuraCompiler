"""Unit tests for computed goto parser support (&&label and goto *expr)."""

from pycc.ast_nodes import (
    LabelAddress, BinaryOp, Assignment, Identifier,
    ComputedGoto, UnaryOp, ArrayAccess, GotoStmt,
)
from pycc.lexer import Lexer
from pycc.parser import Parser


def _parse_expr(code: str):
    """Parse a single expression from a minimal function body."""
    src = f"void f() {{ {code}; }}"
    tokens = Lexer(src).tokenize()
    parser = Parser(tokens)
    program = parser.parse()
    func = program.declarations[0]
    # First statement in the function body
    stmt = func.body.statements[0]
    return stmt.expression if hasattr(stmt, 'expression') else stmt


def _parse_function(code: str):
    """Parse a full function and return the AST."""
    tokens = Lexer(code).tokenize()
    parser = Parser(tokens)
    return parser.parse()


def test_label_address_basic():
    """&&label produces a LabelAddress node."""
    expr = _parse_expr("void *p = &&target")
    # This is an assignment or declaration; get the RHS
    # Actually with DeclStmt, let's parse differently
    src = "void f() { void *p; p = &&target; }"
    tokens = Lexer(src).tokenize()
    parser = Parser(tokens)
    program = parser.parse()
    func = program.declarations[0]
    # Second statement: p = &&target;
    stmt = func.body.statements[1]
    assign = stmt.expression
    assert isinstance(assign, Assignment)
    assert isinstance(assign.value, LabelAddress)
    assert assign.value.label_name == "target"


def test_label_address_in_expression():
    """&&label can appear as a standalone expression."""
    expr = _parse_expr("&&myLabel")
    assert isinstance(expr, LabelAddress)
    assert expr.label_name == "myLabel"


def test_label_address_preserves_line_info():
    """LabelAddress node has line/column info."""
    expr = _parse_expr("&&foo")
    assert isinstance(expr, LabelAddress)
    assert expr.line is not None
    assert expr.line > 0


def test_logical_and_still_works():
    """&& as logical AND between two expressions is not broken."""
    src = "void f() { int a = 1; int b = 2; int c = a && b; }"
    tokens = Lexer(src).tokenize()
    parser = Parser(tokens)
    program = parser.parse()
    func = program.declarations[0]
    # Third statement: int c = a && b;
    # This is a DeclStmt with initializer being BinaryOp
    decl_stmt = func.body.statements[2]
    decl = decl_stmt.declarations[0] if hasattr(decl_stmt, 'declarations') else decl_stmt
    init = decl.initializer
    assert isinstance(init, BinaryOp)
    assert init.operator == "&&"


def test_logical_and_with_non_identifier():
    """&& followed by non-identifier (e.g. number) is logical AND, not label address."""
    src = "void f() { int a = 1; int b = a && 1; }"
    tokens = Lexer(src).tokenize()
    parser = Parser(tokens)
    program = parser.parse()
    func = program.declarations[0]
    decl_stmt = func.body.statements[1]
    decl = decl_stmt.declarations[0] if hasattr(decl_stmt, 'declarations') else decl_stmt
    init = decl.initializer
    assert isinstance(init, BinaryOp)
    assert init.operator == "&&"


# --- Tests for goto *expr (ComputedGoto) ---


def _parse_stmt(code: str):
    """Parse a function body and return the first statement."""
    src = f"void f() {{ {code} }}"
    tokens = Lexer(src).tokenize()
    parser = Parser(tokens)
    program = parser.parse()
    func = program.declarations[0]
    return func.body.statements[0]


def test_computed_goto_basic():
    """goto *ptr produces a ComputedGoto node."""
    stmt = _parse_stmt("void *p; goto *p;")
    # Second statement is the goto *p
    src = "void f() { void *p; goto *p; }"
    tokens = Lexer(src).tokenize()
    parser = Parser(tokens)
    program = parser.parse()
    func = program.declarations[0]
    stmt = func.body.statements[1]
    assert isinstance(stmt, ComputedGoto)
    assert isinstance(stmt.target, Identifier)
    assert stmt.target.name == "p"


def test_computed_goto_deref_expr():
    """goto *table[i] parses the array access expression."""
    src = "void f() { void **table; int i; goto *table[i]; }"
    tokens = Lexer(src).tokenize()
    parser = Parser(tokens)
    program = parser.parse()
    func = program.declarations[0]
    # Third statement: goto *table[i];
    stmt = func.body.statements[2]
    assert isinstance(stmt, ComputedGoto)
    # target is table[i] — an ArrayAccess node
    assert isinstance(stmt.target, ArrayAccess)


def test_computed_goto_preserves_line_info():
    """ComputedGoto node has line/column info."""
    src = "void f() { void *p; goto *p; }"
    tokens = Lexer(src).tokenize()
    parser = Parser(tokens)
    program = parser.parse()
    func = program.declarations[0]
    stmt = func.body.statements[1]
    assert isinstance(stmt, ComputedGoto)
    assert stmt.line is not None
    assert stmt.line > 0


def test_regular_goto_still_works():
    """Regular goto label; is not broken by computed goto support."""
    src = "void f() { goto done; done: return; }"
    tokens = Lexer(src).tokenize()
    parser = Parser(tokens)
    program = parser.parse()
    func = program.declarations[0]
    stmt = func.body.statements[0]
    assert isinstance(stmt, GotoStmt)
    assert stmt.label == "done"
