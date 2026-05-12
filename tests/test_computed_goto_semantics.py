"""Unit tests for computed goto semantic analysis."""

from pycc.lexer import Lexer
from pycc.parser import Parser
from pycc.semantics import SemanticAnalyzer, SemanticError


def _analyze(code: str):
    """Parse and analyze code, return the SemanticAnalyzer instance."""
    tokens = Lexer(code).tokenize()
    ast = Parser(tokens).parse()
    sa = SemanticAnalyzer()
    try:
        sa.analyze(ast)
    except SemanticError:
        pass
    return sa


def test_computed_goto_valid_pointer_target():
    """goto *ptr with a pointer target produces no errors or warnings."""
    code = """
    void f() {
        void *p;
        target:
        p = &&target;
        goto *p;
    }
    """
    sa = _analyze(code)
    assert not sa.errors
    assert not sa.warnings


def test_computed_goto_array_access_target():
    """goto *table[i] with pointer array is valid."""
    code = """
    void f() {
        int i;
        void *table[2];
        lab1:
        lab2:
        table[0] = &&lab1;
        table[1] = &&lab2;
        i = 0;
        goto *table[i];
    }
    """
    sa = _analyze(code)
    assert not sa.errors


def test_computed_goto_non_pointer_target_warns():
    """goto *expr where expr is not a pointer emits a warning."""
    code = """
    void f() {
        int x;
        x = 42;
        goto *x;
    }
    """
    sa = _analyze(code)
    assert not sa.errors
    # Should produce a warning about non-pointer target
    assert any("not a pointer" in w for w in sa.warnings)


def test_computed_goto_analyzes_target_expression():
    """The target expression in goto *expr is analyzed for validity."""
    # Using an undeclared variable should produce an error
    code = """
    void f() {
        goto *undeclared_var;
    }
    """
    sa = _analyze(code)
    # Undeclared variable should trigger an error or warning
    has_issue = bool(sa.errors) or any("undeclared" in w.lower() or "implicit" in w.lower() for w in sa.warnings)
    assert has_issue


def test_label_address_undefined_label_error():
    """&&nonexistent_label produces an error when the label doesn't exist."""
    code = """
    void f() {
        void *p;
        p = &&nonexistent_label;
    }
    """
    sa = _analyze(code)
    assert any("ndefined label" in e and "nonexistent_label" in e for e in sa.errors)


def test_label_address_defined_label_no_error():
    """&&label with a defined label produces no errors."""
    code = """
    void f() {
        void *p;
        target:
        p = &&target;
    }
    """
    sa = _analyze(code)
    assert not sa.errors


def test_label_address_multiple_refs_one_missing():
    """Multiple &&label refs where one label is missing produces an error only for the missing one."""
    code = """
    void f() {
        void *p;
        void *q;
        existing:
        p = &&existing;
        q = &&missing_label;
    }
    """
    sa = _analyze(code)
    assert any("missing_label" in e for e in sa.errors)
    assert not any("existing" in e for e in sa.errors)
