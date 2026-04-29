"""Tests for the unified _parse_declarator method.

Validates that _parse_declarator correctly parses all forms of C declarators:
simple identifiers, pointers, arrays, function declarators, parenthesized
names, function pointers, and complex nested combinations.

Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 4.1, 4.2, 4.3
"""
from __future__ import annotations

import pytest
from pycc.lexer import Lexer, Token, TokenType
from pycc.parser import Parser, DeclaratorInfo
from pycc.ast_nodes import Type


def _make_parser(fragment: str) -> Parser:
    """Create a Parser positioned at the start of a declarator fragment.

    We lex the fragment and append an EOF sentinel so the parser does not
    run off the end.  The caller should invoke parser._parse_declarator()
    directly.
    """
    lexer = Lexer(fragment)
    tokens = lexer.tokenize()
    return Parser(tokens)


class TestSimpleDeclarators:
    """Basic declarator forms: identifier, pointer, const pointer."""

    def test_simple_identifier(self):
        p = _make_parser("x")
        info = p._parse_declarator()
        assert info.name == "x"
        assert info.pointer_level == 0
        assert info.array_dims == []
        assert info.is_function is False
        assert info.is_paren_wrapped is False

    def test_single_pointer(self):
        p = _make_parser("*p")
        info = p._parse_declarator()
        assert info.name == "p"
        assert info.pointer_level == 1
        assert len(info.pointer_quals) == 1
        assert info.pointer_quals[0] == set()

    def test_double_pointer(self):
        p = _make_parser("**pp")
        info = p._parse_declarator()
        assert info.name == "pp"
        assert info.pointer_level == 2
        assert len(info.pointer_quals) == 2

    def test_triple_pointer(self):
        p = _make_parser("***ppp")
        info = p._parse_declarator()
        assert info.name == "ppp"
        assert info.pointer_level == 3

    def test_const_pointer(self):
        p = _make_parser("* const p")
        info = p._parse_declarator()
        assert info.name == "p"
        assert info.pointer_level == 1
        assert "const" in info.pointer_quals[0]

    def test_volatile_pointer(self):
        p = _make_parser("* volatile v")
        info = p._parse_declarator()
        assert info.name == "v"
        assert info.pointer_level == 1
        assert "volatile" in info.pointer_quals[0]

    def test_restrict_pointer(self):
        p = _make_parser("* restrict r")
        info = p._parse_declarator()
        assert info.name == "r"
        assert info.pointer_level == 1
        assert "restrict" in info.pointer_quals[0]

    def test_const_volatile_pointer(self):
        p = _make_parser("* const volatile cv")
        info = p._parse_declarator()
        assert info.name == "cv"
        assert info.pointer_level == 1
        assert "const" in info.pointer_quals[0]
        assert "volatile" in info.pointer_quals[0]

    def test_pointer_to_const_pointer(self):
        """int * const * pp — pointer to const-pointer to int."""
        p = _make_parser("* const *pp")
        info = p._parse_declarator()
        assert info.name == "pp"
        assert info.pointer_level == 2
        # First '*' has const, second '*' has nothing
        # pointer_quals is outermost-first (closest to name first)
        # The second * (outermost, closest to name) has no quals
        # The first * (inner) has const
        assert info.pointer_quals[0] == set()  # outermost
        assert "const" in info.pointer_quals[1]  # inner


class TestArrayDeclarators:
    """Array declarator forms: [N], [], [N][M]."""

    def test_single_array(self):
        p = _make_parser("a[10]")
        info = p._parse_declarator()
        assert info.name == "a"
        assert info.array_dims == [10]
        assert info.pointer_level == 0

    def test_unsized_array(self):
        p = _make_parser("a[]")
        info = p._parse_declarator()
        assert info.name == "a"
        assert info.array_dims == [None]

    def test_multi_dim_array(self):
        p = _make_parser("m[3][4]")
        info = p._parse_declarator()
        assert info.name == "m"
        assert info.array_dims == [3, 4]

    def test_three_dim_array(self):
        p = _make_parser("t[2][3][4]")
        info = p._parse_declarator()
        assert info.name == "t"
        assert info.array_dims == [2, 3, 4]

    def test_pointer_to_array(self):
        """int *a[5] — array of 5 pointers to int."""
        p = _make_parser("*a[5]")
        info = p._parse_declarator()
        assert info.name == "a"
        assert info.pointer_level == 1
        assert info.array_dims == [5]


class TestFunctionDeclarators:
    """Function declarator forms: f(params)."""

    def test_function_no_params(self):
        """int f(void) — note: we pass just the declarator part."""
        p = _make_parser("f()")
        info = p._parse_declarator()
        assert info.name == "f"
        assert info.is_function is True
        assert info.fn_params is not None
        assert len(info.fn_params) == 0

    def test_function_with_params(self):
        p = _make_parser("f(int x, int y)")
        info = p._parse_declarator()
        assert info.name == "f"
        assert info.is_function is True
        assert info.fn_params is not None
        assert len(info.fn_params) == 2

    def test_function_variadic(self):
        p = _make_parser("f(int x, ...)")
        info = p._parse_declarator()
        assert info.name == "f"
        assert info.is_function is True
        assert info.fn_is_variadic is True


class TestParenWrappedDeclarators:
    """Parenthesized declarator forms: (name), (*fp)(params)."""

    def test_paren_wrapped_name(self):
        """int (name) — parenthesized name (Lua style)."""
        p = _make_parser("(name)")
        info = p._parse_declarator()
        assert info.name == "name"
        assert info.is_paren_wrapped is True
        assert info.pointer_level == 0

    def test_function_pointer(self):
        """(*fp)(int) — pointer to function taking int."""
        p = _make_parser("(*fp)(int)")
        info = p._parse_declarator()
        assert info.name == "fp"
        assert info.pointer_level == 1
        assert info.is_function is True
        assert info.is_paren_wrapped is True

    def test_function_pointer_no_name(self):
        """(*)(int, int) — unnamed function pointer (abstract)."""
        p = _make_parser("(*)(int, int)")
        info = p._parse_declarator(allow_abstract=True)
        assert info.name is None
        assert info.pointer_level == 1
        assert info.is_function is True

    def test_paren_wrapped_with_array_suffix(self):
        """(name)[10] — parenthesized name with array suffix."""
        p = _make_parser("(name)[10]")
        info = p._parse_declarator()
        assert info.name == "name"
        assert info.is_paren_wrapped is True
        assert info.array_dims == [10]

    def test_pointer_to_array(self):
        """(*p)[10] — pointer to array of 10."""
        p = _make_parser("(*p)[10]")
        info = p._parse_declarator()
        assert info.name == "p"
        assert info.pointer_level == 1
        assert info.array_dims == [10]
        assert info.is_paren_wrapped is True

    def test_paren_wrapped_function_name(self):
        """(func)(int x) — parenthesized function name with params."""
        p = _make_parser("(func)(int x)")
        info = p._parse_declarator()
        assert info.name == "func"
        assert info.is_paren_wrapped is True
        assert info.is_function is True
        assert info.fn_params is not None
        assert len(info.fn_params) == 1


class TestComplexDeclarators:
    """Complex nested declarator forms."""

    def test_double_pointer_function(self):
        """(**fp)(int) — pointer to pointer to function."""
        p = _make_parser("(**fp)(int)")
        info = p._parse_declarator()
        assert info.name == "fp"
        assert info.pointer_level == 2
        assert info.is_function is True

    def test_function_returning_pointer(self):
        """*f(int) — function returning pointer (not a function pointer)."""
        p = _make_parser("*f(int)")
        info = p._parse_declarator()
        assert info.name == "f"
        assert info.pointer_level == 1
        assert info.is_function is True

    def test_pointer_to_function_returning_pointer_to_array(self):
        """(*(*fp)(int))[10] — pointer to function returning pointer to array."""
        p = _make_parser("(*(*fp)(int))[10]")
        info = p._parse_declarator()
        assert info.name == "fp"
        # The inner (*fp) gives pointer_level=1 from the inner *
        # The outer (*...) gives another pointer level
        # Total: 2 pointer levels
        assert info.pointer_level == 2
        # The (int) is a function suffix on the inner declarator
        assert info.is_function is True
        # The [10] is an array suffix on the outer declarator
        assert info.array_dims == [10]


class TestAbstractDeclarators:
    """Abstract declarators (no name) used in casts and sizeof."""

    def test_abstract_pointer(self):
        p = _make_parser("*")
        info = p._parse_declarator(allow_abstract=True)
        assert info.name is None
        assert info.pointer_level == 1

    def test_abstract_double_pointer(self):
        p = _make_parser("**")
        info = p._parse_declarator(allow_abstract=True)
        assert info.name is None
        assert info.pointer_level == 2

    def test_abstract_no_tokens(self):
        """Empty abstract declarator — just the base type."""
        # When allow_abstract=True and there's nothing to parse,
        # we should get an empty DeclaratorInfo.
        p = _make_parser(";")  # semicolon is not part of declarator
        info = p._parse_declarator(allow_abstract=True)
        assert info.name is None
        assert info.pointer_level == 0
        assert info.array_dims == []

    def test_abstract_raises_without_allow(self):
        """Without allow_abstract, missing name raises ParserError."""
        from pycc.parser import ParserError
        p = _make_parser(";")
        with pytest.raises(ParserError):
            p._parse_declarator(allow_abstract=False)


class TestApplyDeclarator:
    """Tests for _apply_declarator helper."""

    def test_no_pointer(self):
        p = _make_parser("x")
        base = Type(base="int", line=1, column=1)
        info = DeclaratorInfo(name="x", pointer_level=0)
        result = p._apply_declarator(base, info)
        assert result is base  # no copy needed
        assert result.pointer_level == 0

    def test_single_pointer(self):
        p = _make_parser("x")
        base = Type(base="int", line=1, column=1)
        info = DeclaratorInfo(name="p", pointer_level=1, pointer_quals=[set()])
        result = p._apply_declarator(base, info)
        assert result.is_pointer is True
        assert result.pointer_level == 1
        assert result.base == "int"

    def test_const_pointer(self):
        p = _make_parser("x")
        base = Type(base="int", line=1, column=1)
        info = DeclaratorInfo(name="p", pointer_level=1, pointer_quals=[{"const"}])
        result = p._apply_declarator(base, info)
        assert result.is_pointer is True
        assert result.pointer_level == 1
        assert "const" in result.pointer_quals[0]

    def test_preserves_base_qualifiers(self):
        p = _make_parser("x")
        base = Type(base="int", is_const=True, is_unsigned=True, line=1, column=1)
        info = DeclaratorInfo(name="p", pointer_level=1, pointer_quals=[set()])
        result = p._apply_declarator(base, info)
        assert result.is_const is True
        assert result.is_unsigned is True
        assert result.pointer_level == 1

    def test_double_pointer_with_quals(self):
        p = _make_parser("x")
        base = Type(base="char", line=1, column=1)
        info = DeclaratorInfo(
            name="pp",
            pointer_level=2,
            pointer_quals=[set(), {"const"}],
        )
        result = p._apply_declarator(base, info)
        assert result.pointer_level == 2
        assert result.pointer_quals[0] == set()
        assert "const" in result.pointer_quals[1]
