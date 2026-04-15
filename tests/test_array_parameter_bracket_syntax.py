"""Test that array parameter bracket syntax (type name[]) is parsed correctly.

C89 §6.7.1: array parameters are adjusted to pointers.
"""
from pycc.lexer import Lexer
from pycc.parser import Parser
from pycc.ast_nodes import FunctionDecl


def _parse_proto(code: str) -> FunctionDecl:
    tokens = Lexer(code).tokenize()
    prog = Parser(tokens).parse()
    for decl in prog.declarations:
        if isinstance(decl, FunctionDecl):
            return decl
    raise AssertionError(f"No FunctionDecl found in: {code!r}")


class TestArrayParameterBracketSyntax:

    def test_empty_brackets(self):
        """void f(int arr[]) — adjusted to pointer."""
        fd = _parse_proto("void f(int arr[]);")
        assert len(fd.parameters) == 1
        p = fd.parameters[0]
        assert p.name == "arr"
        assert p.type.is_pointer

    def test_sized_brackets(self):
        """void f(int arr[10]) — adjusted to pointer."""
        fd = _parse_proto("void f(int arr[10]);")
        assert len(fd.parameters) == 1
        p = fd.parameters[0]
        assert p.name == "arr"
        assert p.type.is_pointer

    def test_multiple_array_params(self):
        """void f(float a[], float b[], float c[], float d[]) — all adjusted."""
        fd = _parse_proto("void f(float a[], float b[], float c[], float d[]);")
        assert len(fd.parameters) == 4
        for p in fd.parameters:
            assert p.type.is_pointer
            assert p.type.base == "float"

    def test_mixed_array_and_plain(self):
        """void f(int x, float arr[], char *s) — array adjusted, others unchanged."""
        fd = _parse_proto("void f(int x, float arr[], char *s);")
        assert len(fd.parameters) == 3
        assert fd.parameters[0].name == "x"
        assert not fd.parameters[0].type.is_pointer
        assert fd.parameters[1].name == "arr"
        assert fd.parameters[1].type.is_pointer
        assert fd.parameters[2].name == "s"
        assert fd.parameters[2].type.is_pointer

    def test_setmaterial_pattern(self):
        """The exact pattern from mech.c that triggered the bug."""
        fd = _parse_proto("void SetMaterial(float spec[], float amb[], float diff[], float shin[]);")
        assert len(fd.parameters) == 4
        names = [p.name for p in fd.parameters]
        assert names == ["spec", "amb", "diff", "shin"]
        for p in fd.parameters:
            assert p.type.is_pointer
            assert p.type.base == "float"
