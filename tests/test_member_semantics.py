import pytest

from pycc.lexer import Lexer
from pycc.parser import Parser
from pycc.semantics import SemanticAnalyzer, SemanticError


def _analyze(code: str):
    lex = Lexer(code)
    tokens = lex.tokenize()
    p = Parser(tokens)
    ast = p.parse()
    sa = SemanticAnalyzer()
    return sa.analyze(ast)


def test_member_access_unknown_member_is_error():
    code = """
    struct Point { int x; int y; };
    int main() {
        struct Point p;
        return p.z;
    }
    """
    with pytest.raises(SemanticError):
        _analyze(code)


def test_member_access_on_non_struct_is_error():
    code = """
    int main() {
        int x;
        return x.y;
    }
    """
    with pytest.raises(SemanticError):
        _analyze(code)


def test_arrow_on_non_pointer_is_error():
    code = """
    struct S { int x; };
    int main() {
        struct S s;
        return s->x;
    }
    """
    with pytest.raises(SemanticError):
        _analyze(code)


def test_dot_on_pointer_is_error():
    code = """
    struct S { int x; };
    int main() {
        struct S s;
        struct S *p;
        p = &s;
        return p.x;
    }
    """
    with pytest.raises(SemanticError):
        _analyze(code)


def test_arrow_on_pointer_to_non_struct_is_error():
    code = """
    int main() {
        int x;
        int *p;
        p = &x;
        return p->y;
    }
    """
    with pytest.raises(SemanticError):
        _analyze(code)


def test_member_access_ok():
    code = """
    struct Point { int x; int y; };
    int main() {
        struct Point p;
        p.x = 1;
        p.y = 2;
        return p.x + p.y;
    }
    """
    ctx = _analyze(code)
    assert "struct Point" in ctx.layouts
