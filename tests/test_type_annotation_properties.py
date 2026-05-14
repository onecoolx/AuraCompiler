"""Property-based tests for expression type annotation.

Uses Hypothesis to verify that type annotations are correct across
a wide range of randomly generated inputs.

Feature: expr-type-annotation
"""

import pytest
from dataclasses import dataclass
from hypothesis import given, strategies as st, settings

from pycc.semantics import SemanticAnalyzer
from pycc.ast_nodes import IntLiteral, CharLiteral, FloatLiteral, StringLiteral, TernaryOp, Expression, CommaOp, Assignment
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


# =============================================================================
# Property 4: 指针算术类型
# Feature: expr-type-annotation, Property 4: 指针算术类型
# =============================================================================

# Strategy for pointer types
_pointee_types = st.sampled_from([
    IntegerType(kind=TypeKind.INT),
    IntegerType(kind=TypeKind.CHAR),
    IntegerType(kind=TypeKind.LONG),
    FloatType(kind=TypeKind.DOUBLE),
])

_pointer_types = _pointee_types.map(lambda p: PointerType(kind=TypeKind.POINTER, pointee=p))

_integer_types = st.sampled_from([
    IntegerType(kind=TypeKind.CHAR),
    IntegerType(kind=TypeKind.SHORT),
    IntegerType(kind=TypeKind.INT),
    IntegerType(kind=TypeKind.LONG),
    IntegerType(kind=TypeKind.INT, is_unsigned=True),
    IntegerType(kind=TypeKind.LONG, is_unsigned=True),
])


class TestPointerArithmeticTypeProperty:
    """Property 4: 指针算术类型

    For any pointer type P and integer type I, `P + I` and `P - I`'s
    .resolved_type should be P; `P - P`'s .resolved_type should be
    IntegerType(LONG).

    **Validates: Requirements 2.2, 2.3**
    """

    @settings(max_examples=100)
    @given(ptr=_pointer_types, int_t=_integer_types)
    def test_ptr_plus_int_returns_ptr_type(self, ptr, int_t):
        """Pointer + integer yields the pointer type.

        **Validates: Requirements 2.2**
        """
        sa = _make_analyzer()
        result = sa._binary_result_type('+', ptr, int_t)
        assert result == ptr

    @settings(max_examples=100)
    @given(ptr=_pointer_types, int_t=_integer_types)
    def test_int_plus_ptr_returns_ptr_type(self, ptr, int_t):
        """Integer + pointer yields the pointer type.

        **Validates: Requirements 2.2**
        """
        sa = _make_analyzer()
        result = sa._binary_result_type('+', int_t, ptr)
        assert result == ptr

    @settings(max_examples=100)
    @given(ptr=_pointer_types, int_t=_integer_types)
    def test_ptr_minus_int_returns_ptr_type(self, ptr, int_t):
        """Pointer - integer yields the pointer type.

        **Validates: Requirements 2.2**
        """
        sa = _make_analyzer()
        result = sa._binary_result_type('-', ptr, int_t)
        assert result == ptr

    @settings(max_examples=100)
    @given(ptr=_pointer_types)
    def test_ptr_minus_ptr_returns_long(self, ptr):
        """Pointer - pointer yields IntegerType(LONG) (ptrdiff_t).

        **Validates: Requirements 2.3**
        """
        sa = _make_analyzer()
        result = sa._binary_result_type('-', ptr, ptr)
        assert isinstance(result, IntegerType)
        assert result.kind == TypeKind.LONG


# =============================================================================
# Property 5: 比较和逻辑运算符产生 int
# Feature: expr-type-annotation, Property 5: 比较和逻辑运算符产生 int
# =============================================================================

# Strategy for scalar types (integers, floats, pointers)
_scalar_types = st.sampled_from([
    IntegerType(kind=TypeKind.CHAR),
    IntegerType(kind=TypeKind.SHORT),
    IntegerType(kind=TypeKind.INT),
    IntegerType(kind=TypeKind.LONG),
    IntegerType(kind=TypeKind.INT, is_unsigned=True),
    FloatType(kind=TypeKind.FLOAT),
    FloatType(kind=TypeKind.DOUBLE),
    PointerType(kind=TypeKind.POINTER, pointee=IntegerType(kind=TypeKind.INT)),
    PointerType(kind=TypeKind.POINTER, pointee=IntegerType(kind=TypeKind.CHAR)),
])

_relational_ops = st.sampled_from(['<', '<=', '>', '>=', '==', '!='])
_logical_ops = st.sampled_from(['&&', '||'])


class TestComparisonLogicalProduceIntProperty:
    """Property 5: 比较和逻辑运算符产生 int

    For any two scalar types and any relational operator (<, <=, >, >=, ==, !=)
    or logical operator (&&, ||), the result's .resolved_type should be
    IntegerType(INT).

    **Validates: Requirements 2.4, 2.5**
    """

    @settings(max_examples=100)
    @given(left=_scalar_types, right=_scalar_types, op=_relational_ops)
    def test_relational_always_produces_int(self, left, right, op):
        """Relational operators always produce IntegerType(INT).

        **Validates: Requirements 2.4**
        """
        sa = _make_analyzer()
        result = sa._binary_result_type(op, left, right)
        assert isinstance(result, IntegerType)
        assert result.kind == TypeKind.INT

    @settings(max_examples=100)
    @given(left=_scalar_types, right=_scalar_types, op=_logical_ops)
    def test_logical_always_produces_int(self, left, right, op):
        """Logical operators always produce IntegerType(INT).

        **Validates: Requirements 2.5**
        """
        sa = _make_analyzer()
        result = sa._binary_result_type(op, left, right)
        assert isinstance(result, IntegerType)
        assert result.kind == TypeKind.INT


# =============================================================================
# Property 6: 位运算符整数提升
# Feature: expr-type-annotation, Property 6: 位运算符整数提升
# =============================================================================

_integer_types_for_bitwise = st.sampled_from([
    IntegerType(kind=TypeKind.CHAR),
    IntegerType(kind=TypeKind.CHAR, is_unsigned=True),
    IntegerType(kind=TypeKind.SHORT),
    IntegerType(kind=TypeKind.SHORT, is_unsigned=True),
    IntegerType(kind=TypeKind.INT),
    IntegerType(kind=TypeKind.INT, is_unsigned=True),
    IntegerType(kind=TypeKind.LONG),
    IntegerType(kind=TypeKind.LONG, is_unsigned=True),
])

_bitwise_ops = st.sampled_from(['&', '|', '^', '<<', '>>'])


class TestBitwiseIntegerPromotionProperty:
    """Property 6: 位运算符整数提升

    For any two integer types L and R, and any bitwise operator (&, |, ^, <<, >>),
    the result's .resolved_type should equal the result of performing UAC on the
    promoted operand types.

    **Validates: Requirements 2.6**
    """

    @settings(max_examples=100)
    @given(left=_integer_types_for_bitwise, right=_integer_types_for_bitwise, op=_bitwise_ops)
    def test_bitwise_result_equals_uac_of_promoted(self, left, right, op):
        """Bitwise operator result type equals UAC(promote(left), promote(right)).

        **Validates: Requirements 2.6**
        """
        sa = _make_analyzer()
        result = sa._binary_result_type(op, left, right)
        expected = usual_arithmetic_conversions(
            integer_promote(left), integer_promote(right))
        assert result == expected


# =============================================================================
# Property 7: 三元运算符算术 UAC
# Feature: expr-type-annotation, Property 7: 三元运算符算术 UAC
# =============================================================================


@dataclass
class _TypedExpr(Expression):
    """A dummy expression node with a pre-set resolved_type.

    _analyze_expr won't recognize this subclass, so it won't overwrite
    the resolved_type we set. This lets us control the branch types
    for testing the ternary operator's UAC logic.
    """
    pass


def _make_typed_expr(ctype):
    """Create a dummy expression with a given resolved_type."""
    expr = _TypedExpr(line=1, column=1)
    expr.resolved_type = ctype
    return expr


class TestTernaryArithmeticUACProperty:
    """Property 7: 三元运算符算术 UAC

    For any two arithmetic types used as the true/false branches of a ternary
    operator, the result's .resolved_type should equal
    usual_arithmetic_conversions(true_type, false_type).

    **Validates: Requirements 2.7**
    """

    @settings(max_examples=100)
    @given(true_type=_arithmetic_types, false_type=_arithmetic_types)
    def test_ternary_arithmetic_result_equals_uac(self, true_type, false_type):
        """Ternary with arithmetic branches produces UAC(promote(true), promote(false)).

        **Validates: Requirements 2.7**
        """
        sa = _make_analyzer()

        # Create condition expression (IntLiteral will get resolved_type=INT)
        condition = IntLiteral(value=1, line=1, column=1)
        # Create true/false branch expressions with pre-set resolved_type
        # Using _TypedExpr so _analyze_expr won't overwrite the type
        true_expr = _make_typed_expr(true_type)
        false_expr = _make_typed_expr(false_type)

        # Build TernaryOp node
        ternary = TernaryOp(
            condition=condition,
            true_expr=true_expr,
            false_expr=false_expr,
            line=1, column=1,
        )

        sa._analyze_expr(ternary)

        expected = usual_arithmetic_conversions(
            integer_promote(true_type), integer_promote(false_type))
        assert ternary.resolved_type == expected


# =============================================================================
# Property 9: 取地址/解引用 round-trip
# Feature: expr-type-annotation, Property 9: 取地址/解引用 round-trip
# =============================================================================

_base_types_for_unary = st.sampled_from([
    IntegerType(kind=TypeKind.CHAR),
    IntegerType(kind=TypeKind.SHORT),
    IntegerType(kind=TypeKind.INT),
    IntegerType(kind=TypeKind.LONG),
    IntegerType(kind=TypeKind.INT, is_unsigned=True),
    FloatType(kind=TypeKind.FLOAT),
    FloatType(kind=TypeKind.DOUBLE),
    PointerType(kind=TypeKind.POINTER, pointee=IntegerType(kind=TypeKind.INT)),
    PointerType(kind=TypeKind.POINTER, pointee=IntegerType(kind=TypeKind.CHAR)),
])


class TestAddressDerefRoundTripProperty:
    """Property 9: 取地址/解引用 round-trip

    For any type T, `&expr` of type T produces PointerType(pointee=T);
    For any PointerType(pointee=T), `*expr` produces T.
    Thus `*(&expr)` has the same type as expr (round-trip).

    **Validates: Requirements 3.1, 3.2**
    """

    @settings(max_examples=100)
    @given(t=_base_types_for_unary)
    def test_address_of_produces_pointer(self, t):
        """&expr of type T produces PointerType(pointee=T).

        **Validates: Requirements 3.1**
        """
        sa = _make_analyzer()
        result = sa._unary_result_type('&', t)
        assert isinstance(result, PointerType)
        assert result.kind == TypeKind.POINTER
        assert result.pointee == t

    @settings(max_examples=100)
    @given(t=_base_types_for_unary)
    def test_deref_of_pointer_produces_pointee(self, t):
        """*expr of type PointerType(pointee=T) produces T.

        **Validates: Requirements 3.2**
        """
        sa = _make_analyzer()
        ptr = PointerType(kind=TypeKind.POINTER, pointee=t)
        result = sa._unary_result_type('*', ptr)
        assert result == t

    @settings(max_examples=100)
    @given(t=_base_types_for_unary)
    def test_deref_address_of_round_trip(self, t):
        """*(&expr) has the same type as expr (round-trip).

        **Validates: Requirements 3.1, 3.2**
        """
        sa = _make_analyzer()
        addr = sa._unary_result_type('&', t)
        result = sa._unary_result_type('*', addr)
        assert result == t


# =============================================================================
# Property 10: 一元提升运算符
# Feature: expr-type-annotation, Property 10: 一元提升运算符
# =============================================================================

_integer_types_for_unary = st.sampled_from([
    IntegerType(kind=TypeKind.CHAR),
    IntegerType(kind=TypeKind.CHAR, is_unsigned=True),
    IntegerType(kind=TypeKind.SHORT),
    IntegerType(kind=TypeKind.SHORT, is_unsigned=True),
    IntegerType(kind=TypeKind.INT),
    IntegerType(kind=TypeKind.INT, is_unsigned=True),
    IntegerType(kind=TypeKind.LONG),
    IntegerType(kind=TypeKind.LONG, is_unsigned=True),
])

_unary_promote_ops = st.sampled_from(['~', '+', '-'])


class TestUnaryPromotionProperty:
    """Property 10: 一元提升运算符

    For any integer type T and unary operator ~, +, -, the result's
    .resolved_type should equal integer_promote(T).

    **Validates: Requirements 3.4, 3.5**
    """

    @settings(max_examples=100)
    @given(t=_integer_types_for_unary, op=_unary_promote_ops)
    def test_unary_promotion_equals_integer_promote(self, t, op):
        """Unary ~, +, - on integer type T produces integer_promote(T).

        **Validates: Requirements 3.4, 3.5**
        """
        sa = _make_analyzer()
        result = sa._unary_result_type(op, t)
        expected = integer_promote(t)
        assert result == expected


# =============================================================================
# Property 8: 逗号和赋值类型规则
# Feature: expr-type-annotation, Property 8: 逗号和赋值类型规则
# =============================================================================

# Strategy for generating random CTypes for comma/assignment tests
_all_ctypes_for_comma_assign = st.sampled_from([
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
    PointerType(kind=TypeKind.POINTER, pointee=IntegerType(kind=TypeKind.INT)),
    PointerType(kind=TypeKind.POINTER, pointee=IntegerType(kind=TypeKind.CHAR)),
    PointerType(kind=TypeKind.POINTER, pointee=FloatType(kind=TypeKind.DOUBLE)),
])


class TestCommaAndAssignmentTypeRulesProperty:
    """Property 8: 逗号和赋值类型规则

    For any comma expression `(a, b)`, .resolved_type should equal b's type;
    For any assignment expression `a = b`, .resolved_type should equal a's type.

    **Validates: Requirements 2.9, 2.10**
    """

    @settings(max_examples=100)
    @given(left_type=_all_ctypes_for_comma_assign, right_type=_all_ctypes_for_comma_assign)
    def test_comma_result_type_equals_right_operand(self, left_type, right_type):
        """CommaOp (a, b) has resolved_type equal to b's type.

        **Validates: Requirements 2.9**
        """
        sa = _make_analyzer()

        # Create left and right expressions with pre-set resolved_type
        left_expr = _make_typed_expr(left_type)
        right_expr = _make_typed_expr(right_type)

        # Build CommaOp node
        comma = CommaOp(
            left=left_expr,
            right=right_expr,
            line=1, column=1,
        )

        sa._analyze_expr(comma)

        assert comma.resolved_type == right_type

    @settings(max_examples=100)
    @given(left_type=_all_ctypes_for_comma_assign, right_type=_all_ctypes_for_comma_assign)
    def test_assignment_result_type_equals_left_operand(self, left_type, right_type):
        """Assignment (a = b) has resolved_type equal to a's type.

        **Validates: Requirements 2.10**
        """
        sa = _make_analyzer()

        # Create target and value expressions with pre-set resolved_type
        target_expr = _make_typed_expr(left_type)
        value_expr = _make_typed_expr(right_type)

        # Build Assignment node
        assign = Assignment(
            target=target_expr,
            operator='=',
            value=value_expr,
            line=1, column=1,
        )

        sa._analyze_expr(assign)

        assert assign.resolved_type == left_type

    @settings(max_examples=100)
    @given(
        left_type=_all_ctypes_for_comma_assign,
        mid_type=_all_ctypes_for_comma_assign,
        right_type=_all_ctypes_for_comma_assign,
    )
    def test_nested_comma_result_type_equals_rightmost(self, left_type, mid_type, right_type):
        """Nested comma (a, (b, c)) has resolved_type equal to c's type.

        **Validates: Requirements 2.9**
        """
        sa = _make_analyzer()

        left_expr = _make_typed_expr(left_type)
        mid_expr = _make_typed_expr(mid_type)
        right_expr = _make_typed_expr(right_type)

        # Inner comma: (b, c) -> type of c
        inner_comma = CommaOp(
            left=mid_expr,
            right=right_expr,
            line=1, column=1,
        )

        # Outer comma: (a, (b, c)) -> type of inner comma = type of c
        outer_comma = CommaOp(
            left=left_expr,
            right=inner_comma,
            line=1, column=1,
        )

        sa._analyze_expr(outer_comma)

        assert outer_comma.resolved_type == right_type

    @settings(max_examples=100)
    @given(
        assign_ops=st.sampled_from(['=', '+=', '-=', '*=', '/=', '%=']),
        left_type=_all_ctypes_for_comma_assign,
        right_type=_all_ctypes_for_comma_assign,
    )
    def test_compound_assignment_result_type_equals_left(self, assign_ops, left_type, right_type):
        """Compound assignment (a op= b) has resolved_type equal to a's type.

        **Validates: Requirements 2.10**
        """
        sa = _make_analyzer()

        target_expr = _make_typed_expr(left_type)
        value_expr = _make_typed_expr(right_type)

        assign = Assignment(
            target=target_expr,
            operator=assign_ops,
            value=value_expr,
            line=1, column=1,
        )

        sa._analyze_expr(assign)

        assert assign.resolved_type == left_type


# =============================================================================
# Property 14: 下标运算类型
# Feature: expr-type-annotation, Property 14: 下标运算类型
# =============================================================================

from pycc.ast_nodes import ArrayAccess

# Strategy for element types used in array/pointer subscript tests
_element_types_for_subscript = st.sampled_from([
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
    PointerType(kind=TypeKind.POINTER, pointee=IntegerType(kind=TypeKind.INT)),
    PointerType(kind=TypeKind.POINTER, pointee=IntegerType(kind=TypeKind.CHAR)),
])


class TestSubscriptOperatorTypeProperty:
    """Property 14: 下标运算类型

    For any ArrayType(element=T) or PointerType(pointee=T) expression,
    the subscript operation `expr[i]` should have .resolved_type equal to T.

    **Validates: Requirements 4.1, 4.2**
    """

    @settings(max_examples=100)
    @given(elem_type=_element_types_for_subscript,
           array_size=st.integers(min_value=1, max_value=100))
    def test_array_subscript_yields_element_type(self, elem_type, array_size):
        """ArrayType(element=T)[i] has resolved_type == T.

        **Validates: Requirements 4.1**
        """
        sa = _make_analyzer()

        # Create base expression with ArrayType resolved_type
        array_ct = ArrayType(kind=TypeKind.ARRAY, element=elem_type, size=array_size)
        base_expr = _make_typed_expr(array_ct)

        # Create index expression (integer literal)
        index_expr = IntLiteral(value=0, line=1, column=1)

        # Build ArrayAccess node
        access = ArrayAccess(
            array=base_expr,
            index=index_expr,
            line=1, column=1,
        )

        sa._analyze_expr(access)

        assert access.resolved_type is not None
        assert access.resolved_type == elem_type

    @settings(max_examples=100)
    @given(elem_type=_element_types_for_subscript)
    def test_pointer_subscript_yields_pointee_type(self, elem_type):
        """PointerType(pointee=T)[i] has resolved_type == T.

        **Validates: Requirements 4.2**
        """
        sa = _make_analyzer()

        # Create base expression with PointerType resolved_type
        ptr_ct = PointerType(kind=TypeKind.POINTER, pointee=elem_type)
        base_expr = _make_typed_expr(ptr_ct)

        # Create index expression (integer literal)
        index_expr = IntLiteral(value=0, line=1, column=1)

        # Build ArrayAccess node
        access = ArrayAccess(
            array=base_expr,
            index=index_expr,
            line=1, column=1,
        )

        sa._analyze_expr(access)

        assert access.resolved_type is not None
        assert access.resolved_type == elem_type

    @settings(max_examples=100)
    @given(
        elem_type=_element_types_for_subscript,
        use_array=st.booleans(),
        array_size=st.integers(min_value=1, max_value=50),
        index_val=st.integers(min_value=0, max_value=49),
    )
    def test_subscript_type_independent_of_index_value(self, elem_type, use_array, array_size, index_val):
        """Subscript result type is T regardless of the index value used.

        **Validates: Requirements 4.1, 4.2**
        """
        sa = _make_analyzer()

        # Create base with either ArrayType or PointerType
        if use_array:
            base_ct = ArrayType(kind=TypeKind.ARRAY, element=elem_type, size=array_size)
        else:
            base_ct = PointerType(kind=TypeKind.POINTER, pointee=elem_type)

        base_expr = _make_typed_expr(base_ct)
        index_expr = IntLiteral(value=index_val, line=1, column=1)

        access = ArrayAccess(
            array=base_expr,
            index=index_expr,
            line=1, column=1,
        )

        sa._analyze_expr(access)

        assert access.resolved_type is not None
        assert access.resolved_type == elem_type


# =============================================================================
# Property 17: _expr_type 兼容性
# Feature: expr-type-annotation, Property 17: _expr_type 兼容性
# =============================================================================

from pycc.types import ctype_to_ast_type, StructType, EnumType, CType, ast_type_to_ctype


# Strategy for all CType variants that can appear as resolved_type
_all_resolved_ctypes = st.sampled_from([
    # Integer types
    IntegerType(kind=TypeKind.CHAR),
    IntegerType(kind=TypeKind.CHAR, is_unsigned=True),
    IntegerType(kind=TypeKind.SHORT),
    IntegerType(kind=TypeKind.SHORT, is_unsigned=True),
    IntegerType(kind=TypeKind.INT),
    IntegerType(kind=TypeKind.INT, is_unsigned=True),
    IntegerType(kind=TypeKind.LONG),
    IntegerType(kind=TypeKind.LONG, is_unsigned=True),
    # Float types
    FloatType(kind=TypeKind.FLOAT),
    FloatType(kind=TypeKind.DOUBLE),
    # Pointer types
    PointerType(kind=TypeKind.POINTER, pointee=IntegerType(kind=TypeKind.INT)),
    PointerType(kind=TypeKind.POINTER, pointee=IntegerType(kind=TypeKind.CHAR)),
    PointerType(kind=TypeKind.POINTER, pointee=FloatType(kind=TypeKind.DOUBLE)),
    PointerType(kind=TypeKind.POINTER, pointee=CType(kind=TypeKind.VOID)),
    # Double pointer
    PointerType(kind=TypeKind.POINTER, pointee=PointerType(kind=TypeKind.POINTER, pointee=IntegerType(kind=TypeKind.INT))),
    # Struct/Union types
    StructType(kind=TypeKind.STRUCT, tag='MyStruct'),
    StructType(kind=TypeKind.UNION, tag='MyUnion'),
    # Enum type
    EnumType(kind=TypeKind.ENUM, tag='Color'),
    # Void type
    CType(kind=TypeKind.VOID),
])


class TestExprTypeCompatibilityProperty:
    """Property 17: _expr_type 兼容性

    For any expression node with .resolved_type set, calling _expr_type()
    returns an ast_nodes.Type that is semantically equivalent to the
    .resolved_type (same base type, pointer level, signedness, etc.).

    **Validates: Requirements 6.3**
    """

    @settings(max_examples=100)
    @given(ct=_all_resolved_ctypes)
    def test_expr_type_returns_equivalent_ast_type(self, ct):
        """_expr_type() on a node with resolved_type returns semantically equivalent Type.

        **Validates: Requirements 6.3**
        """
        sa = _make_analyzer()

        # Create a dummy expression with resolved_type set
        expr = _make_typed_expr(ct)

        # Call _expr_type which should use the resolved_type path
        result = sa._expr_type(expr)

        # Verify result is not None
        assert result is not None, f"_expr_type returned None for resolved_type={ct}"

        # Convert back to CType and verify round-trip equivalence
        round_trip = ast_type_to_ctype(result)

        # Verify kind matches
        assert round_trip.kind == ct.kind, (
            f"Kind mismatch: expected {ct.kind}, got {round_trip.kind} "
            f"(resolved_type={ct}, ast_type={result})"
        )

    @settings(max_examples=100)
    @given(ct=_all_resolved_ctypes)
    def test_expr_type_pointer_level_matches(self, ct):
        """_expr_type() preserves pointer level from resolved_type.

        **Validates: Requirements 6.3**
        """
        sa = _make_analyzer()
        expr = _make_typed_expr(ct)
        result = sa._expr_type(expr)

        assert result is not None

        # Count pointer depth in the CType
        expected_ptr_level = 0
        inner = ct
        while isinstance(inner, PointerType):
            expected_ptr_level += 1
            inner = inner.pointee if inner.pointee else CType(kind=TypeKind.VOID)

        # Check the ast_nodes.Type pointer_level
        actual_ptr_level = getattr(result, 'pointer_level', 0) or 0
        assert actual_ptr_level == expected_ptr_level, (
            f"Pointer level mismatch: expected {expected_ptr_level}, "
            f"got {actual_ptr_level} for resolved_type={ct}"
        )

    @settings(max_examples=100)
    @given(
        base=st.sampled_from(['int', 'char', 'short', 'long']),
        is_unsigned=st.booleans(),
    )
    def test_expr_type_preserves_signedness(self, base, is_unsigned):
        """_expr_type() preserves unsigned flag from resolved_type.

        **Validates: Requirements 6.3**
        """
        kind_map = {'int': TypeKind.INT, 'char': TypeKind.CHAR,
                    'short': TypeKind.SHORT, 'long': TypeKind.LONG}
        ct = IntegerType(kind=kind_map[base], is_unsigned=is_unsigned)

        sa = _make_analyzer()
        expr = _make_typed_expr(ct)
        result = sa._expr_type(expr)

        assert result is not None
        assert getattr(result, 'is_unsigned', False) == is_unsigned, (
            f"Unsigned mismatch: expected {is_unsigned}, "
            f"got {getattr(result, 'is_unsigned', False)} for {ct}"
        )

    @settings(max_examples=100)
    @given(ct=_all_resolved_ctypes)
    def test_expr_type_base_name_correct(self, ct):
        """_expr_type() produces correct base name for the resolved_type.

        **Validates: Requirements 6.3**
        """
        sa = _make_analyzer()
        expr = _make_typed_expr(ct)
        result = sa._expr_type(expr)

        assert result is not None
        base = getattr(result, 'base', '')

        # Verify base name matches the CType kind
        if ct.kind == TypeKind.INT:
            assert base == 'int'
        elif ct.kind == TypeKind.CHAR:
            assert base == 'char'
        elif ct.kind == TypeKind.SHORT:
            assert base == 'short'
        elif ct.kind == TypeKind.LONG:
            assert base == 'long'
        elif ct.kind == TypeKind.FLOAT:
            assert base == 'float'
        elif ct.kind == TypeKind.DOUBLE:
            assert base == 'double'
        elif ct.kind == TypeKind.VOID:
            assert base == 'void'
        elif ct.kind == TypeKind.POINTER:
            # For pointers, base is the innermost non-pointer type's base
            inner = ct
            while isinstance(inner, PointerType):
                inner = inner.pointee if inner.pointee else CType(kind=TypeKind.VOID)
            inner_ast = ctype_to_ast_type(inner)
            assert base == getattr(inner_ast, 'base', ''), (
                f"Pointer base mismatch: expected '{getattr(inner_ast, 'base', '')}', got '{base}'"
            )
        elif ct.kind == TypeKind.STRUCT:
            assert 'struct' in base or 'union' in base
        elif ct.kind == TypeKind.UNION:
            assert 'union' in base
        elif ct.kind == TypeKind.ENUM:
            assert 'enum' in base

    @settings(max_examples=100)
    @given(ct=_all_resolved_ctypes)
    def test_expr_type_is_pointer_flag_correct(self, ct):
        """_expr_type() sets is_pointer correctly based on resolved_type.

        **Validates: Requirements 6.3**
        """
        sa = _make_analyzer()
        expr = _make_typed_expr(ct)
        result = sa._expr_type(expr)

        assert result is not None

        is_ptr_type = isinstance(ct, PointerType)
        result_is_ptr = getattr(result, 'is_pointer', False)

        assert result_is_ptr == is_ptr_type, (
            f"is_pointer mismatch: expected {is_ptr_type}, "
            f"got {result_is_ptr} for resolved_type={ct}"
        )
