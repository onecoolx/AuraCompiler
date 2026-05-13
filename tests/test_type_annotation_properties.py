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


# =============================================================================
# Property 2: 标识符类型解析（含 typedef）
# Feature: expr-type-annotation, Property 2: 标识符类型解析
# =============================================================================


from pycc.ast_nodes import Identifier, Type as ASTType
from pycc.types import ArrayType


# Strategies for generating random type configurations
_BASE_TYPES = ['int', 'char', 'short', 'long', 'float', 'double']
_INTEGER_BASES = ['int', 'char', 'short', 'long']
_FLOAT_BASES = ['float', 'double']

# Map base type strings to expected TypeKind
_BASE_TO_KIND = {
    'int': TypeKind.INT,
    'char': TypeKind.CHAR,
    'short': TypeKind.SHORT,
    'long': TypeKind.LONG,
    'float': TypeKind.FLOAT,
    'double': TypeKind.DOUBLE,
}


def _make_analyzer_with_decl(name, ast_type, typedefs=None):
    """Create a SemanticAnalyzer with a declared identifier and optional typedefs."""
    sa = SemanticAnalyzer()
    sa._decl_types = {name: ast_type}
    sa._global_decl_types = {}
    if typedefs:
        sa._typedefs = [typedefs]
    else:
        sa._typedefs = [{}]
    return sa


class TestIdentifierTypeResolutionProperty:
    """Property 2: 标识符类型解析（含 typedef）

    For any declared identifier (including those declared with typedef types),
    its .resolved_type should equal the declared type converted to CType
    after typedef recursive resolution.

    **Validates: Requirements 1.6, 7.3**
    """

    @settings(max_examples=100)
    @given(
        base=st.sampled_from(_BASE_TYPES),
        var_name=st.from_regex(r'[a-z][a-z0-9_]{0,9}', fullmatch=True),
    )
    def test_basic_type_identifier_resolves_correctly(self, base, var_name):
        """Identifier declared with a basic type resolves to the corresponding CType.

        **Validates: Requirements 1.6**
        """
        ast_type = ASTType(line=0, column=0, base=base)
        sa = _make_analyzer_with_decl(var_name, ast_type)
        expr = Identifier(name=var_name, line=1, column=1)
        sa._analyze_expr(expr)

        assert expr.resolved_type is not None
        expected_kind = _BASE_TO_KIND[base]
        assert expr.resolved_type.kind == expected_kind

    @settings(max_examples=100)
    @given(
        base=st.sampled_from(_BASE_TYPES),
        ptr_level=st.integers(min_value=1, max_value=3),
        var_name=st.from_regex(r'[a-z][a-z0-9_]{0,9}', fullmatch=True),
    )
    def test_pointer_type_identifier_resolves_correctly(self, base, ptr_level, var_name):
        """Identifier declared as pointer type resolves to PointerType with correct depth.

        **Validates: Requirements 1.6**
        """
        ast_type = ASTType(
            line=0, column=0, base=base,
            is_pointer=True, pointer_level=ptr_level,
        )
        sa = _make_analyzer_with_decl(var_name, ast_type)
        expr = Identifier(name=var_name, line=1, column=1)
        sa._analyze_expr(expr)

        assert expr.resolved_type is not None
        # Walk the pointer chain
        ct = expr.resolved_type
        for _ in range(ptr_level):
            assert isinstance(ct, PointerType), f"Expected PointerType, got {ct}"
            assert ct.kind == TypeKind.POINTER
            ct = ct.pointee
        # The innermost type should match the base
        expected_kind = _BASE_TO_KIND[base]
        assert ct.kind == expected_kind

    @settings(max_examples=100)
    @given(
        base=st.sampled_from(_BASE_TYPES),
        typedef_name=st.from_regex(r'[A-Z][a-zA-Z0-9_]{2,8}', fullmatch=True),
        var_name=st.from_regex(r'[a-z][a-z0-9_]{0,9}', fullmatch=True),
    )
    def test_typedef_identifier_resolves_to_underlying_type(self, base, typedef_name, var_name):
        """Identifier declared with a typedef name resolves to the underlying type.

        **Validates: Requirements 1.6, 7.3**
        """
        # Define typedef: typedef_name -> base type
        typedef_target = ASTType(line=0, column=0, base=base)
        typedefs = {typedef_name: typedef_target}

        # Declare variable with the typedef name as its base type
        var_type = ASTType(line=0, column=0, base=typedef_name)
        sa = _make_analyzer_with_decl(var_name, var_type, typedefs=typedefs)
        expr = Identifier(name=var_name, line=1, column=1)
        sa._analyze_expr(expr)

        assert expr.resolved_type is not None
        expected_kind = _BASE_TO_KIND[base]
        assert expr.resolved_type.kind == expected_kind

    @settings(max_examples=100)
    @given(
        base=st.sampled_from(_BASE_TYPES),
        chain_length=st.integers(min_value=2, max_value=4),
        var_name=st.from_regex(r'[a-z][a-z0-9_]{0,9}', fullmatch=True),
    )
    def test_typedef_chain_resolves_to_final_underlying_type(self, base, chain_length, var_name):
        """Typedef chain (A -> B -> C -> int) resolves to the final underlying type.

        **Validates: Requirements 7.3**
        """
        # Build a chain of typedefs: T0 -> T1 -> ... -> base
        typedefs = {}
        names = [f"Type_{i}" for i in range(chain_length)]
        # Last typedef points to the base type
        typedefs[names[-1]] = ASTType(line=0, column=0, base=base)
        # Each earlier typedef points to the next one
        for i in range(chain_length - 1):
            typedefs[names[i]] = ASTType(line=0, column=0, base=names[i + 1])

        # Declare variable with the first typedef name
        var_type = ASTType(line=0, column=0, base=names[0])
        sa = _make_analyzer_with_decl(var_name, var_type, typedefs=typedefs)
        expr = Identifier(name=var_name, line=1, column=1)
        sa._analyze_expr(expr)

        assert expr.resolved_type is not None
        expected_kind = _BASE_TO_KIND[base]
        assert expr.resolved_type.kind == expected_kind

    @settings(max_examples=100)
    @given(
        base=st.sampled_from(_BASE_TYPES),
        typedef_name=st.from_regex(r'[A-Z][a-zA-Z0-9_]{2,8}', fullmatch=True),
        ptr_level=st.integers(min_value=1, max_value=2),
        var_name=st.from_regex(r'[a-z][a-z0-9_]{0,9}', fullmatch=True),
    )
    def test_typedef_pointer_identifier_resolves_correctly(self, base, typedef_name, ptr_level, var_name):
        """Identifier declared as pointer-to-typedef resolves correctly.

        e.g. typedef int MyInt; MyInt *p; -> p is PointerType(pointee=IntegerType(INT))

        **Validates: Requirements 1.6, 7.3**
        """
        # Define typedef: typedef_name -> base type
        typedef_target = ASTType(line=0, column=0, base=base)
        typedefs = {typedef_name: typedef_target}

        # Declare variable as pointer to typedef
        var_type = ASTType(
            line=0, column=0, base=typedef_name,
            is_pointer=True, pointer_level=ptr_level,
        )
        sa = _make_analyzer_with_decl(var_name, var_type, typedefs=typedefs)
        expr = Identifier(name=var_name, line=1, column=1)
        sa._analyze_expr(expr)

        assert expr.resolved_type is not None
        # Walk the pointer chain
        ct = expr.resolved_type
        for _ in range(ptr_level):
            assert isinstance(ct, PointerType)
            ct = ct.pointee
        # The innermost type should be the resolved typedef base
        expected_kind = _BASE_TO_KIND[base]
        assert ct.kind == expected_kind

    @settings(max_examples=100)
    @given(
        base=st.sampled_from(_BASE_TYPES),
        array_size=st.integers(min_value=1, max_value=100),
        var_name=st.from_regex(r'[a-z][a-z0-9_]{0,9}', fullmatch=True),
    )
    def test_array_identifier_decays_to_pointer(self, base, array_size, var_name):
        """Array identifier decays to pointer type in expression context.

        int arr[10] -> arr has resolved_type PointerType(pointee=IntegerType(INT))

        **Validates: Requirements 1.6**
        """
        elem_type = ASTType(line=0, column=0, base=base)
        var_type = ASTType(
            line=0, column=0, base=base,
            is_array=True,
            array_element_type=elem_type,
            array_dimensions=[array_size],
        )
        sa = _make_analyzer_with_decl(var_name, var_type)
        expr = Identifier(name=var_name, line=1, column=1)
        sa._analyze_expr(expr)

        assert expr.resolved_type is not None
        # Array decays to pointer
        assert isinstance(expr.resolved_type, PointerType)
        assert expr.resolved_type.kind == TypeKind.POINTER
        # Pointee should be the element type
        expected_kind = _BASE_TO_KIND[base]
        assert expr.resolved_type.pointee.kind == expected_kind

    @settings(max_examples=100)
    @given(
        base=st.sampled_from(_INTEGER_BASES),
        is_unsigned=st.booleans(),
        var_name=st.from_regex(r'[a-z][a-z0-9_]{0,9}', fullmatch=True),
    )
    def test_unsigned_type_identifier_preserves_signedness(self, base, is_unsigned, var_name):
        """Identifier with unsigned qualifier preserves signedness in resolved_type.

        **Validates: Requirements 1.6**
        """
        ast_type = ASTType(line=0, column=0, base=base, is_unsigned=is_unsigned)
        sa = _make_analyzer_with_decl(var_name, ast_type)
        expr = Identifier(name=var_name, line=1, column=1)
        sa._analyze_expr(expr)

        assert expr.resolved_type is not None
        expected_kind = _BASE_TO_KIND[base]
        assert expr.resolved_type.kind == expected_kind
        assert isinstance(expr.resolved_type, IntegerType)
        assert expr.resolved_type.is_unsigned == is_unsigned


# =============================================================================
# Property 3: 算术二元运算符 UAC
# Feature: expr-type-annotation, Property 3: 算术二元运算符 UAC
# =============================================================================

from pycc.types import integer_promote, usual_arithmetic_conversions

# Strategy for generating arithmetic CTypes
_arithmetic_types = st.sampled_from([
    IntegerType(kind=TypeKind.CHAR),
    IntegerType(kind=TypeKind.CHAR, is_unsigned=True),
    IntegerType(kind=TypeKind.SHORT),
    IntegerType(kind=TypeKind.SHORT, is_unsigned=True),
    IntegerType(kind=TypeKind.INT),
    IntegerType(kind=TypeKind.INT, is_unsigned=True),
    IntegerType(kind=TypeKind.LONG),
    IntegerType(kind=TypeKind.LONG, is_unsigned=True),
    FloatType(kind=TypeKind.FLOAT),
    FloatType(kind=TypeKind.DOUBLE),
])

_arithmetic_ops = st.sampled_from(['+', '-', '*', '/', '%'])


class TestArithmeticBinaryUACProperty:
    """Property 3: 算术二元运算符 UAC

    For any two arithmetic types L and R, and any arithmetic operator
    (+, -, *, /, %), the binary expression's .resolved_type should equal
    usual_arithmetic_conversions(integer_promote(L), integer_promote(R)).

    **Validates: Requirements 2.1**
    """

    @settings(max_examples=100)
    @given(left=_arithmetic_types, right=_arithmetic_types, op=_arithmetic_ops)
    def test_arithmetic_binary_result_equals_uac(self, left, right, op):
        """Binary arithmetic result type equals UAC(promote(left), promote(right)).

        **Validates: Requirements 2.1**
        """
        sa = _make_analyzer()
        result = sa._binary_result_type(op, left, right)
        expected = usual_arithmetic_conversions(
            integer_promote(left), integer_promote(right))
        assert result == expected
