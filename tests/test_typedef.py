import pytest

from pycc.lexer import Lexer
from pycc.parser import Parser
from pycc.semantics import SemanticAnalyzer, SemanticError
from pycc.ast_nodes import TypedefDecl


def test_typedef_parsing():
    code = """
    typedef int myint;
    myint x;
    """
    lex = Lexer(code)
    tokens = lex.tokenize()
    assert not lex.has_errors()

    p = Parser(tokens)
    ast = p.parse()
    # top-level typedef should be present
    typedefs = [d for d in ast.declarations if isinstance(d, TypedefDecl)]
    assert len(typedefs) == 1
    assert typedefs[0].name == "myint"


def test_typedef_semantics_registration():
    code = """
    typedef int myint;
    myint x;
    """
    lex = Lexer(code)
    tokens = lex.tokenize()
    p = Parser(tokens)
    ast = p.parse()

    sa = SemanticAnalyzer()
    # should not raise
    ctx = sa.analyze(ast)
    assert "myint" in ctx.typedefs
