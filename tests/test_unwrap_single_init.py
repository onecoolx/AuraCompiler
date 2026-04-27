"""Unit tests for IRGenerator._unwrap_single_init helper."""

import pytest
from pycc.ast_nodes import (
    Initializer,
    Designator,
    IntLiteral,
    FloatLiteral,
    Identifier,
    StringLiteral,
)
from pycc.ir import IRGenerator

# Shorthand: all test AST nodes use dummy location (0, 0).
L, C = 0, 0


class TestUnwrapSingleInit:
    """Tests for _unwrap_single_init static method."""

    def test_unwrap_single_int_in_braces(self):
        """int x = {42} -> unwraps to IntLiteral(42)."""
        inner = IntLiteral(L, C, value=42)
        init = Initializer(L, C, elements=[(None, inner)])
        result = IRGenerator._unwrap_single_init(init)
        assert result is inner

    def test_unwrap_single_float_in_braces(self):
        """float f = {3.14} -> unwraps to FloatLiteral."""
        inner = FloatLiteral(L, C, value=3.14)
        init = Initializer(L, C, elements=[(None, inner)])
        result = IRGenerator._unwrap_single_init(init)
        assert result is inner

    def test_unwrap_single_identifier_in_braces(self):
        """int x = {y} -> unwraps to Identifier."""
        inner = Identifier(L, C, name="y")
        init = Initializer(L, C, elements=[(None, inner)])
        result = IRGenerator._unwrap_single_init(init)
        assert result is inner

    def test_no_unwrap_multiple_elements(self):
        """int a[] = {1, 2} -> returns original Initializer."""
        init = Initializer(L, C, elements=[
            (None, IntLiteral(L, C, value=1)),
            (None, IntLiteral(L, C, value=2)),
        ])
        result = IRGenerator._unwrap_single_init(init)
        assert result is init

    def test_no_unwrap_with_designator(self):
        """.x = 42 -> single element but has designator, returns original."""
        desig = Designator(L, C, member="x")
        init = Initializer(L, C, elements=[(desig, IntLiteral(L, C, value=42))])
        result = IRGenerator._unwrap_single_init(init)
        assert result is init

    def test_no_unwrap_empty_initializer(self):
        """{} -> empty initializer, returns original."""
        init = Initializer(L, C, elements=[])
        result = IRGenerator._unwrap_single_init(init)
        assert result is init

    def test_passthrough_non_initializer(self):
        """Plain expression (not wrapped in braces) passes through."""
        expr = IntLiteral(L, C, value=99)
        result = IRGenerator._unwrap_single_init(expr)
        assert result is expr

    def test_passthrough_string_literal(self):
        """StringLiteral passes through unchanged."""
        expr = StringLiteral(L, C, value="hello")
        result = IRGenerator._unwrap_single_init(expr)
        assert result is expr

    def test_nested_initializer_unwraps_one_level(self):
        """{{1, 2}} -> single element is itself an Initializer, unwraps one level."""
        inner_init = Initializer(L, C, elements=[
            (None, IntLiteral(L, C, value=1)),
            (None, IntLiteral(L, C, value=2)),
        ])
        outer = Initializer(L, C, elements=[(None, inner_init)])
        result = IRGenerator._unwrap_single_init(outer)
        assert result is inner_init
