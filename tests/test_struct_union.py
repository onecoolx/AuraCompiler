import pytest

from pycc.lexer import Lexer
from pycc.parser import Parser
from pycc.semantics import SemanticAnalyzer


def test_struct_declaration_parses_as_type_specifier():
    code = """
    struct Point { int x; int y; };
    int main() { return 0; }
    """
    lex = Lexer(code)
    tokens = lex.tokenize()
    assert not lex.has_errors()

    p = Parser(tokens)
    ast = p.parse()
    assert ast is not None


def test_struct_variable_declaration_parses():
    code = """
    struct Point { int x; int y; };
    struct Point p;
    int main() { return 0; }
    """
    lex = Lexer(code)
    tokens = lex.tokenize()
    p = Parser(tokens)
    ast = p.parse()
    # semantic analyzer should accept and produce layout
    sa = SemanticAnalyzer()
    ctx = sa.analyze(ast)
    assert "struct Point" in ctx.layouts
    assert ctx.layouts["struct Point"].member_offsets["x"] == 0
    assert ctx.layouts["struct Point"].member_offsets["y"] == 4


def test_struct_pointer_declaration_parses():
    code = """
    struct S { int x; };
    int main() {
        struct S s;
        struct S *p;
        p = &s;
        return 0;
    }
    """
    lex = Lexer(code)
    tokens = lex.tokenize()
    ast = Parser(tokens).parse()
    ctx = SemanticAnalyzer().analyze(ast)
    assert "struct S" in ctx.layouts


def test_union_declaration_parses():
    code = """
    union U { int x; char y; };
    int main() { return 0; }
    """
    lex = Lexer(code)
    tokens = lex.tokenize()
    p = Parser(tokens)
    ast = p.parse()
    sa = SemanticAnalyzer()
    ctx = sa.analyze(ast)
    assert "union U" in ctx.layouts
    assert ctx.layouts["union U"].member_offsets["x"] == 0
    assert ctx.layouts["union U"].member_offsets["y"] == 0
