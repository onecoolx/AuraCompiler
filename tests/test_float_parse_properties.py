"""Property tests: float explicit conversion (Property 23)."""
import pytest
from pycc.lexer import Lexer
from pycc.parser import Parser
from pycc.ast_nodes import FloatLiteral


def test_float_literal_parsed():
    code = "float x = 3.14f;"
    l = Lexer(code, "<test>")
    t = l.tokenize()
    p = Parser(t)
    ast = p.parse()
    assert ast.declarations[0].type.base == "float"
    assert isinstance(ast.declarations[0].initializer, FloatLiteral)
    assert abs(ast.declarations[0].initializer.value - 3.14) < 0.01


def test_double_literal_parsed():
    code = "double y = 1.0e-5;"
    l = Lexer(code, "<test>")
    t = l.tokenize()
    p = Parser(t)
    ast = p.parse()
    assert ast.declarations[0].type.base == "double"
    assert isinstance(ast.declarations[0].initializer, FloatLiteral)


def test_float_type_in_ctype():
    from pycc.types import ast_type_to_ctype, TypeKind
    from pycc.ast_nodes import Type
    t = Type(line=0, column=0, base="float")
    ct = ast_type_to_ctype(t)
    assert ct.kind == TypeKind.FLOAT


def test_double_type_in_ctype():
    from pycc.types import ast_type_to_ctype, TypeKind
    from pycc.ast_nodes import Type
    t = Type(line=0, column=0, base="double")
    ct = ast_type_to_ctype(t)
    assert ct.kind == TypeKind.DOUBLE
