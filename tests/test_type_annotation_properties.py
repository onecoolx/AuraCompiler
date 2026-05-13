"""Property-based tests for expression type annotation.

Uses Hypothesis to verify that type annotations are correct across
a wide range of randomly generated inputs.

Feature: expr-type-annotation
"""

import pytest
from hypothesis import given, strategies as st, settings

from pycc.semantics import SemanticAnalyzer
from pycc.ast_nodes import IntLiteral, CharLiteral, FloatLiteral, StringLiteral
from pycc.types import (
    FloatType,
    IntegerType,
    PointerType,
    TypeKind,
)


@pytest.fixture
def analyzer():
    """Create a SemanticAnalyzer with minimal state for testing."""
    sa = SemanticAnalyzer()
    sa._decl_types = {}
    sa._global_decl_types = {}
    return sa


def _make_analyzer():
    """Create a SemanticAnalyzer instance for use in property tests."""
    sa = SemanticAnalyzer()
    sa._decl_types = {}
    sa._global_decl_types = {}
    return sa


# =============================================================================
# Property 1: 字面量类型标注正确性
# Feature: expr-type-annotation, Property 1: 字面量类型标注正确性
# =============================================================================


class TestLiteralTypeAnnotationProperty:
    """Property 1: 字面量类型标注正确性

    For any integer literal, character literal, float literal, or string literal,
    after semantic analysis, its .resolved_type should be IntegerType(INT),
    IntegerType(INT), FloatType(DOUBLE), PointerType(pointee=IntegerType(CHAR))
    respectively.

    **Validates: Requirements 1.2, 1.3, 1.4, 1.5**
    """

    @settings(max_examples=100)
    @given(value=st.integers(min_value=-2**31, max_value=2**31 - 1))
    def test_int_literal_always_int_type(self, value):
        """IntLiteral always gets IntegerType(INT).

        **Validates: Requirements 1.2**
        """
        sa = _make_analyzer()
        expr = IntLiteral(value=value, line=1, column=1)
        sa._analyze_expr(expr)
        assert isinstance(expr.resolved_type, IntegerType)
        assert expr.resolved_type.kind == TypeKind.INT

    @settings(max_examples=100)
    @given(value=st.integers(min_value=0, max_value=2**32 - 1))
    def test_int_literal_unsigned_range_still_int(self, value):
        """IntLiteral with large unsigned values still gets IntegerType(INT).

        **Validates: Requirements 1.2**
        """
        sa = _make_analyzer()
        expr = IntLiteral(value=value, line=1, column=1)
        sa._analyze_expr(expr)
        assert isinstance(expr.resolved_type, IntegerType)
        assert expr.resolved_type.kind == TypeKind.INT

    @settings(max_examples=100)
    @given(char=st.characters(min_codepoint=1, max_codepoint=127))
    def test_char_literal_always_int_type(self, char):
        """CharLiteral always gets IntegerType(INT) per C89 rules.

        **Validates: Requirements 1.3**
        """
        sa = _make_analyzer()
        expr = CharLiteral(value=char, line=1, column=1)
        sa._analyze_expr(expr)
        assert isinstance(expr.resolved_type, IntegerType)
        assert expr.resolved_type.kind == TypeKind.INT

    @settings(max_examples=100)
    @given(value=st.floats(allow_nan=False, allow_infinity=False,
                           min_value=-1e308, max_value=1e308))
    def test_float_literal_no_suffix_always_double(self, value):
        """FloatLiteral without suffix always gets FloatType(DOUBLE).

        **Validates: Requirements 1.4**
        """
        sa = _make_analyzer()
        expr = FloatLiteral(value=value, suffix='', line=1, column=1)
        sa._analyze_expr(expr)
        assert isinstance(expr.resolved_type, FloatType)
        assert expr.resolved_type.kind == TypeKind.DOUBLE

    @settings(max_examples=100)
    @given(value=st.floats(allow_nan=False, allow_infinity=False,
                           min_value=-1e38, max_value=1e38),
           suffix=st.sampled_from(['f', 'F']))
    def test_float_literal_f_suffix_always_float(self, value, suffix):
        """FloatLiteral with 'f'/'F' suffix gets FloatType(FLOAT).

        **Validates: Requirements 1.4**
        """
        sa = _make_analyzer()
        expr = FloatLiteral(value=value, suffix=suffix, line=1, column=1)
        sa._analyze_expr(expr)
        assert isinstance(expr.resolved_type, FloatType)
        assert expr.resolved_type.kind == TypeKind.FLOAT

    @settings(max_examples=100)
    @given(value=st.text(
        alphabet=st.characters(min_codepoint=32, max_codepoint=126),
        min_size=0, max_size=100))
    def test_string_literal_always_pointer_to_char(self, value):
        """StringLiteral always gets PointerType(pointee=IntegerType(CHAR)).

        **Validates: Requirements 1.5**
        """
        sa = _make_analyzer()
        expr = StringLiteral(value=value, line=1, column=1)
        sa._analyze_expr(expr)
        assert isinstance(expr.resolved_type, PointerType)
        assert expr.resolved_type.kind == TypeKind.POINTER
        assert isinstance(expr.resolved_type.pointee, IntegerType)
        assert expr.resolved_type.pointee.kind == TypeKind.CHAR
