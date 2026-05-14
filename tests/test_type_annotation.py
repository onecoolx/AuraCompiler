"""Unit tests for expression type annotation skeleton methods.

Tests _annotate_type, _resolve_identifier_ctype, and _decay_type methods
added to SemanticAnalyzer as part of the expr-type-annotation feature.
"""

import pytest

from pycc.semantics import SemanticAnalyzer
from pycc.ast_nodes import Type as ASTType
from pycc.types import (
    ArrayType,
    CType,
    FloatType,
    FunctionTypeCType,
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


class TestAnnotateType:
    """Tests for _annotate_type method."""

    def test_sets_resolved_type(self, analyzer):
        class Expr:
            pass

        expr = Expr()
        ct = IntegerType(kind=TypeKind.INT)
        analyzer._annotate_type(expr, ct)
        assert expr.resolved_type is ct

    def test_returns_ctype(self, analyzer):
        class Expr:
            pass

        expr = Expr()
        ct = FloatType(kind=TypeKind.DOUBLE)
        result = analyzer._annotate_type(expr, ct)
        assert result is ct

    def test_none_ctype(self, analyzer):
        class Expr:
            pass

        expr = Expr()
        result = analyzer._annotate_type(expr, None)
        assert expr.resolved_type is None
        assert result is None


class TestDecayType:
    """Tests for _decay_type method."""

    def test_array_decays_to_pointer(self, analyzer):
        elem = IntegerType(kind=TypeKind.INT)
        arr = ArrayType(kind=TypeKind.ARRAY, element=elem, size=5)
        result = analyzer._decay_type(arr)
        assert isinstance(result, PointerType)
        assert result.kind == TypeKind.POINTER
        assert result.pointee is elem

    def test_function_decays_to_pointer(self, analyzer):
        func = FunctionTypeCType(
            kind=TypeKind.FUNCTION,
            return_type=IntegerType(kind=TypeKind.INT),
            param_types=[IntegerType(kind=TypeKind.INT)],
        )
        result = analyzer._decay_type(func)
        assert isinstance(result, PointerType)
        assert result.kind == TypeKind.POINTER
        assert result.pointee is func

    def test_integer_passthrough(self, analyzer):
        ct = IntegerType(kind=TypeKind.INT)
        assert analyzer._decay_type(ct) is ct

    def test_pointer_passthrough(self, analyzer):
        ct = PointerType(kind=TypeKind.POINTER, pointee=IntegerType(kind=TypeKind.INT))
        assert analyzer._decay_type(ct) is ct

    def test_float_passthrough(self, analyzer):
        ct = FloatType(kind=TypeKind.DOUBLE)
        assert analyzer._decay_type(ct) is ct

    def test_none_returns_none(self, analyzer):
        assert analyzer._decay_type(None) is None

    def test_array_of_pointers_decays(self, analyzer):
        elem = PointerType(kind=TypeKind.POINTER, pointee=IntegerType(kind=TypeKind.CHAR))
        arr = ArrayType(kind=TypeKind.ARRAY, element=elem, size=3)
        result = analyzer._decay_type(arr)
        assert isinstance(result, PointerType)
        assert result.pointee is elem


class TestResolveIdentifierCtype:
    """Tests for _resolve_identifier_ctype method."""

    def test_not_found_returns_none(self, analyzer):
        assert analyzer._resolve_identifier_ctype("unknown") is None

    def test_local_int(self, analyzer):
        analyzer._decl_types = {"x": ASTType(line=0, column=0, base="int")}
        result = analyzer._resolve_identifier_ctype("x")
        assert result is not None
        assert result.kind == TypeKind.INT

    def test_local_pointer(self, analyzer):
        analyzer._decl_types = {
            "p": ASTType(line=0, column=0, base="int", is_pointer=True, pointer_level=1)
        }
        result = analyzer._resolve_identifier_ctype("p")
        assert isinstance(result, PointerType)
        assert result.kind == TypeKind.POINTER
        assert result.pointee.kind == TypeKind.INT

    def test_global_fallback(self, analyzer):
        analyzer._decl_types = {}
        analyzer._global_decl_types = {"g": ASTType(line=0, column=0, base="long")}
        result = analyzer._resolve_identifier_ctype("g")
        assert result is not None
        assert result.kind == TypeKind.LONG

    def test_local_shadows_global(self, analyzer):
        analyzer._decl_types = {"x": ASTType(line=0, column=0, base="char")}
        analyzer._global_decl_types = {"x": ASTType(line=0, column=0, base="long")}
        result = analyzer._resolve_identifier_ctype("x")
        assert result.kind == TypeKind.CHAR

    def test_typedef_resolution(self, analyzer):
        # Set up a typedef: MyInt -> int
        analyzer._typedefs = [{"MyInt": ASTType(line=0, column=0, base="int")}]
        analyzer._decl_types = {"v": ASTType(line=0, column=0, base="MyInt")}
        result = analyzer._resolve_identifier_ctype("v")
        assert result is not None
        assert result.kind == TypeKind.INT

    def test_unsigned_int(self, analyzer):
        analyzer._decl_types = {
            "u": ASTType(line=0, column=0, base="int", is_unsigned=True)
        }
        result = analyzer._resolve_identifier_ctype("u")
        assert result is not None
        assert result.kind == TypeKind.INT
        assert result.is_unsigned is True

    def test_double_pointer(self, analyzer):
        analyzer._decl_types = {
            "pp": ASTType(line=0, column=0, base="char", is_pointer=True, pointer_level=2)
        }
        result = analyzer._resolve_identifier_ctype("pp")
        assert isinstance(result, PointerType)
        assert isinstance(result.pointee, PointerType)
        assert result.pointee.pointee.kind == TypeKind.CHAR


class TestLiteralTypeAnnotation:
    """Tests for literal type annotation in _analyze_expr (task 2.1)."""

    def test_int_literal_type(self, analyzer):
        from pycc.ast_nodes import IntLiteral
        expr = IntLiteral(value=42, line=1, column=1)
        analyzer._analyze_expr(expr)
        assert isinstance(expr.resolved_type, IntegerType)
        assert expr.resolved_type.kind == TypeKind.INT

    def test_int_literal_zero(self, analyzer):
        from pycc.ast_nodes import IntLiteral
        expr = IntLiteral(value=0, line=1, column=1)
        analyzer._analyze_expr(expr)
        assert isinstance(expr.resolved_type, IntegerType)
        assert expr.resolved_type.kind == TypeKind.INT

    def test_char_literal_type(self, analyzer):
        from pycc.ast_nodes import CharLiteral
        expr = CharLiteral(value='a', line=1, column=1)
        analyzer._analyze_expr(expr)
        assert isinstance(expr.resolved_type, IntegerType)
        assert expr.resolved_type.kind == TypeKind.INT

    def test_float_literal_double(self, analyzer):
        from pycc.ast_nodes import FloatLiteral
        expr = FloatLiteral(value=3.14, line=1, column=1)
        analyzer._analyze_expr(expr)
        assert isinstance(expr.resolved_type, FloatType)
        assert expr.resolved_type.kind == TypeKind.DOUBLE

    def test_float_literal_float_suffix_lower(self, analyzer):
        from pycc.ast_nodes import FloatLiteral
        expr = FloatLiteral(value=3.14, suffix='f', line=1, column=1)
        analyzer._analyze_expr(expr)
        assert isinstance(expr.resolved_type, FloatType)
        assert expr.resolved_type.kind == TypeKind.FLOAT

    def test_float_literal_float_suffix_upper(self, analyzer):
        from pycc.ast_nodes import FloatLiteral
        expr = FloatLiteral(value=3.14, suffix='F', line=1, column=1)
        analyzer._analyze_expr(expr)
        assert isinstance(expr.resolved_type, FloatType)
        assert expr.resolved_type.kind == TypeKind.FLOAT

    def test_float_literal_long_double_suffix(self, analyzer):
        from pycc.ast_nodes import FloatLiteral
        # 'L' suffix means long double, but for now we treat it as DOUBLE
        # since the design says only f/F -> FLOAT, otherwise DOUBLE
        expr = FloatLiteral(value=3.14, suffix='L', line=1, column=1)
        analyzer._analyze_expr(expr)
        assert isinstance(expr.resolved_type, FloatType)
        assert expr.resolved_type.kind == TypeKind.DOUBLE

    def test_string_literal_type(self, analyzer):
        from pycc.ast_nodes import StringLiteral
        expr = StringLiteral(value='hello', line=1, column=1)
        analyzer._analyze_expr(expr)
        assert isinstance(expr.resolved_type, PointerType)
        assert expr.resolved_type.kind == TypeKind.POINTER
        assert isinstance(expr.resolved_type.pointee, IntegerType)
        assert expr.resolved_type.pointee.kind == TypeKind.CHAR

    def test_empty_string_literal_type(self, analyzer):
        from pycc.ast_nodes import StringLiteral
        expr = StringLiteral(value='', line=1, column=1)
        analyzer._analyze_expr(expr)
        assert isinstance(expr.resolved_type, PointerType)
        assert expr.resolved_type.pointee.kind == TypeKind.CHAR


class TestIdentifierTypeAnnotation:
    """Tests for Identifier type annotation in _analyze_expr (task 2.2)."""

    def test_identifier_int_variable(self, analyzer):
        from pycc.ast_nodes import Identifier
        analyzer._decl_types = {"x": ASTType(line=0, column=0, base="int")}
        expr = Identifier(name="x", line=1, column=1)
        analyzer._analyze_expr(expr)
        assert isinstance(expr.resolved_type, IntegerType)
        assert expr.resolved_type.kind == TypeKind.INT

    def test_identifier_pointer_variable(self, analyzer):
        from pycc.ast_nodes import Identifier
        analyzer._decl_types = {
            "p": ASTType(line=0, column=0, base="int", is_pointer=True, pointer_level=1)
        }
        expr = Identifier(name="p", line=1, column=1)
        analyzer._analyze_expr(expr)
        assert isinstance(expr.resolved_type, PointerType)
        assert expr.resolved_type.pointee.kind == TypeKind.INT

    def test_identifier_array_decays_to_pointer(self, analyzer):
        from pycc.ast_nodes import Identifier
        analyzer._decl_types = {
            "arr": ASTType(line=0, column=0, base="int", is_array=True, array_dimensions=[10])
        }
        expr = Identifier(name="arr", line=1, column=1)
        analyzer._analyze_expr(expr)
        # Array should decay to pointer in expression context
        assert isinstance(expr.resolved_type, PointerType)
        assert expr.resolved_type.pointee.kind == TypeKind.INT

    def test_identifier_enum_constant(self, analyzer):
        from pycc.ast_nodes import Identifier
        analyzer._enum_constants = {"RED": 0, "GREEN": 1, "BLUE": 2}
        expr = Identifier(name="RED", line=1, column=1)
        analyzer._analyze_expr(expr)
        assert isinstance(expr.resolved_type, IntegerType)
        assert expr.resolved_type.kind == TypeKind.INT

    def test_identifier_undeclared_gets_none(self, analyzer):
        from pycc.ast_nodes import Identifier
        # Undeclared identifier - resolved_type should be None
        expr = Identifier(name="unknown", line=1, column=1)
        analyzer._analyze_expr(expr)
        assert expr.resolved_type is None

    def test_identifier_global_variable(self, analyzer):
        from pycc.ast_nodes import Identifier
        analyzer._decl_types = {}
        analyzer._global_decl_types = {"g": ASTType(line=0, column=0, base="long")}
        expr = Identifier(name="g", line=1, column=1)
        analyzer._analyze_expr(expr)
        assert isinstance(expr.resolved_type, IntegerType)
        assert expr.resolved_type.kind == TypeKind.LONG

    def test_identifier_typedef_resolved(self, analyzer):
        from pycc.ast_nodes import Identifier
        analyzer._typedefs = [{"size_t": ASTType(line=0, column=0, base="long", is_unsigned=True)}]
        analyzer._decl_types = {"n": ASTType(line=0, column=0, base="size_t")}
        expr = Identifier(name="n", line=1, column=1)
        analyzer._analyze_expr(expr)
        assert isinstance(expr.resolved_type, IntegerType)
        assert expr.resolved_type.kind == TypeKind.LONG
        assert expr.resolved_type.is_unsigned is True

    def test_identifier_char_array_decays(self, analyzer):
        from pycc.ast_nodes import Identifier
        analyzer._decl_types = {
            "buf": ASTType(line=0, column=0, base="char", is_array=True, array_dimensions=[256])
        }
        expr = Identifier(name="buf", line=1, column=1)
        analyzer._analyze_expr(expr)
        # char[] decays to char*
        assert isinstance(expr.resolved_type, PointerType)
        assert expr.resolved_type.pointee.kind == TypeKind.CHAR

    def test_identifier_double_variable(self, analyzer):
        from pycc.ast_nodes import Identifier
        analyzer._decl_types = {"d": ASTType(line=0, column=0, base="double")}
        expr = Identifier(name="d", line=1, column=1)
        analyzer._analyze_expr(expr)
        assert isinstance(expr.resolved_type, FloatType)
        assert expr.resolved_type.kind == TypeKind.DOUBLE


class TestBinaryResultType:
    """Tests for _binary_result_type method (task 3.1)."""

    def test_none_left_returns_none(self, analyzer):
        r = analyzer._binary_result_type('+', None, IntegerType(kind=TypeKind.INT))
        assert r is None

    def test_none_right_returns_none(self, analyzer):
        r = analyzer._binary_result_type('+', IntegerType(kind=TypeKind.INT), None)
        assert r is None

    def test_both_none_returns_none(self, analyzer):
        r = analyzer._binary_result_type('+', None, None)
        assert r is None

    # -- Arithmetic operators with UAC --

    def test_int_plus_int(self, analyzer):
        r = analyzer._binary_result_type('+', IntegerType(kind=TypeKind.INT),
                                         IntegerType(kind=TypeKind.INT))
        assert r == IntegerType(kind=TypeKind.INT)

    def test_int_plus_long_promotes_to_long(self, analyzer):
        r = analyzer._binary_result_type('+', IntegerType(kind=TypeKind.INT),
                                         IntegerType(kind=TypeKind.LONG))
        assert r == IntegerType(kind=TypeKind.LONG)

    def test_short_minus_short_promotes_to_int(self, analyzer):
        r = analyzer._binary_result_type('-', IntegerType(kind=TypeKind.SHORT),
                                         IntegerType(kind=TypeKind.SHORT))
        assert r == IntegerType(kind=TypeKind.INT)

    def test_char_mult_char_promotes_to_int(self, analyzer):
        r = analyzer._binary_result_type('*', IntegerType(kind=TypeKind.CHAR),
                                         IntegerType(kind=TypeKind.CHAR))
        assert r == IntegerType(kind=TypeKind.INT)

    def test_int_div_double_promotes_to_double(self, analyzer):
        r = analyzer._binary_result_type('/', IntegerType(kind=TypeKind.INT),
                                         FloatType(kind=TypeKind.DOUBLE))
        assert r == FloatType(kind=TypeKind.DOUBLE)

    def test_float_mod_int(self, analyzer):
        # float % int -> UAC -> float (after promotion)
        r = analyzer._binary_result_type('%', FloatType(kind=TypeKind.FLOAT),
                                         IntegerType(kind=TypeKind.INT))
        # UAC: float vs int -> float (float has higher rank than int)
        assert isinstance(r, FloatType)

    # -- Pointer arithmetic --

    def test_ptr_plus_int(self, analyzer):
        ptr = PointerType(kind=TypeKind.POINTER, pointee=IntegerType(kind=TypeKind.INT))
        r = analyzer._binary_result_type('+', ptr, IntegerType(kind=TypeKind.INT))
        assert r is ptr

    def test_int_plus_ptr(self, analyzer):
        ptr = PointerType(kind=TypeKind.POINTER, pointee=IntegerType(kind=TypeKind.CHAR))
        r = analyzer._binary_result_type('+', IntegerType(kind=TypeKind.LONG), ptr)
        assert r is ptr

    def test_ptr_minus_int(self, analyzer):
        ptr = PointerType(kind=TypeKind.POINTER, pointee=FloatType(kind=TypeKind.DOUBLE))
        r = analyzer._binary_result_type('-', ptr, IntegerType(kind=TypeKind.INT))
        assert r is ptr

    def test_ptr_minus_ptr_is_long(self, analyzer):
        ptr = PointerType(kind=TypeKind.POINTER, pointee=IntegerType(kind=TypeKind.INT))
        r = analyzer._binary_result_type('-', ptr, ptr)
        assert r == IntegerType(kind=TypeKind.LONG)

    def test_ptr_plus_ptr_is_invalid(self, analyzer):
        ptr = PointerType(kind=TypeKind.POINTER, pointee=IntegerType(kind=TypeKind.INT))
        r = analyzer._binary_result_type('+', ptr, ptr)
        assert r is None

    def test_int_minus_ptr_is_invalid(self, analyzer):
        ptr = PointerType(kind=TypeKind.POINTER, pointee=IntegerType(kind=TypeKind.INT))
        r = analyzer._binary_result_type('-', IntegerType(kind=TypeKind.INT), ptr)
        assert r is None

    # -- Relational operators --

    def test_less_than_returns_int(self, analyzer):
        r = analyzer._binary_result_type('<', IntegerType(kind=TypeKind.LONG),
                                         IntegerType(kind=TypeKind.INT))
        assert r == IntegerType(kind=TypeKind.INT)

    def test_greater_equal_returns_int(self, analyzer):
        r = analyzer._binary_result_type('>=', FloatType(kind=TypeKind.DOUBLE),
                                         IntegerType(kind=TypeKind.INT))
        assert r == IntegerType(kind=TypeKind.INT)

    def test_equal_returns_int(self, analyzer):
        ptr = PointerType(kind=TypeKind.POINTER, pointee=IntegerType(kind=TypeKind.INT))
        r = analyzer._binary_result_type('==', ptr, ptr)
        assert r == IntegerType(kind=TypeKind.INT)

    def test_not_equal_returns_int(self, analyzer):
        r = analyzer._binary_result_type('!=', IntegerType(kind=TypeKind.CHAR),
                                         IntegerType(kind=TypeKind.INT))
        assert r == IntegerType(kind=TypeKind.INT)

    # -- Logical operators --

    def test_logical_and_returns_int(self, analyzer):
        r = analyzer._binary_result_type('&&', IntegerType(kind=TypeKind.INT),
                                         IntegerType(kind=TypeKind.INT))
        assert r == IntegerType(kind=TypeKind.INT)

    def test_logical_or_returns_int(self, analyzer):
        r = analyzer._binary_result_type('||', FloatType(kind=TypeKind.DOUBLE),
                                         IntegerType(kind=TypeKind.INT))
        assert r == IntegerType(kind=TypeKind.INT)

    # -- Bitwise operators --

    def test_bitwise_and_short_short_promotes_to_int(self, analyzer):
        r = analyzer._binary_result_type('&', IntegerType(kind=TypeKind.SHORT),
                                         IntegerType(kind=TypeKind.SHORT))
        assert r == IntegerType(kind=TypeKind.INT)

    def test_bitwise_or_int_long_promotes_to_long(self, analyzer):
        r = analyzer._binary_result_type('|', IntegerType(kind=TypeKind.INT),
                                         IntegerType(kind=TypeKind.LONG))
        assert r == IntegerType(kind=TypeKind.LONG)

    def test_bitwise_xor_char_int(self, analyzer):
        r = analyzer._binary_result_type('^', IntegerType(kind=TypeKind.CHAR),
                                         IntegerType(kind=TypeKind.INT))
        assert r == IntegerType(kind=TypeKind.INT)

    def test_left_shift_int_int(self, analyzer):
        r = analyzer._binary_result_type('<<', IntegerType(kind=TypeKind.INT),
                                         IntegerType(kind=TypeKind.INT))
        assert r == IntegerType(kind=TypeKind.INT)

    def test_right_shift_long_int(self, analyzer):
        r = analyzer._binary_result_type('>>', IntegerType(kind=TypeKind.LONG),
                                         IntegerType(kind=TypeKind.INT))
        assert r == IntegerType(kind=TypeKind.LONG)

    # -- Unknown operator --

    def test_unknown_op_returns_none(self, analyzer):
        r = analyzer._binary_result_type('???', IntegerType(kind=TypeKind.INT),
                                         IntegerType(kind=TypeKind.INT))
        assert r is None


class TestUnaryResultType:
    """Tests for _unary_result_type method (task 5.1)."""

    def test_none_operand_returns_none(self, analyzer):
        r = analyzer._unary_result_type('&', None)
        assert r is None

    # -- Address-of (&) --

    def test_address_of_int(self, analyzer):
        operand = IntegerType(kind=TypeKind.INT)
        r = analyzer._unary_result_type('&', operand)
        assert isinstance(r, PointerType)
        assert r.kind == TypeKind.POINTER
        assert r.pointee is operand

    def test_address_of_pointer(self, analyzer):
        inner = PointerType(kind=TypeKind.POINTER, pointee=IntegerType(kind=TypeKind.CHAR))
        r = analyzer._unary_result_type('&', inner)
        assert isinstance(r, PointerType)
        assert r.pointee is inner

    def test_address_of_float(self, analyzer):
        operand = FloatType(kind=TypeKind.DOUBLE)
        r = analyzer._unary_result_type('&', operand)
        assert isinstance(r, PointerType)
        assert r.pointee is operand

    # -- Dereference (*) --

    def test_deref_pointer_to_int(self, analyzer):
        pointee = IntegerType(kind=TypeKind.INT)
        ptr = PointerType(kind=TypeKind.POINTER, pointee=pointee)
        r = analyzer._unary_result_type('*', ptr)
        assert r is pointee

    def test_deref_pointer_to_pointer(self, analyzer):
        inner = PointerType(kind=TypeKind.POINTER, pointee=IntegerType(kind=TypeKind.CHAR))
        ptr = PointerType(kind=TypeKind.POINTER, pointee=inner)
        r = analyzer._unary_result_type('*', ptr)
        assert r is inner

    def test_deref_non_pointer_returns_none(self, analyzer):
        r = analyzer._unary_result_type('*', IntegerType(kind=TypeKind.INT))
        assert r is None

    def test_deref_float_returns_none(self, analyzer):
        r = analyzer._unary_result_type('*', FloatType(kind=TypeKind.DOUBLE))
        assert r is None

    # -- Logical not (!) --

    def test_logical_not_int(self, analyzer):
        r = analyzer._unary_result_type('!', IntegerType(kind=TypeKind.INT))
        assert r == IntegerType(kind=TypeKind.INT)

    def test_logical_not_pointer(self, analyzer):
        ptr = PointerType(kind=TypeKind.POINTER, pointee=IntegerType(kind=TypeKind.INT))
        r = analyzer._unary_result_type('!', ptr)
        assert r == IntegerType(kind=TypeKind.INT)

    def test_logical_not_float(self, analyzer):
        r = analyzer._unary_result_type('!', FloatType(kind=TypeKind.DOUBLE))
        assert r == IntegerType(kind=TypeKind.INT)

    # -- Bitwise not (~) --

    def test_bitwise_not_int(self, analyzer):
        r = analyzer._unary_result_type('~', IntegerType(kind=TypeKind.INT))
        assert r == IntegerType(kind=TypeKind.INT)

    def test_bitwise_not_char_promotes_to_int(self, analyzer):
        r = analyzer._unary_result_type('~', IntegerType(kind=TypeKind.CHAR))
        assert r == IntegerType(kind=TypeKind.INT)

    def test_bitwise_not_short_promotes_to_int(self, analyzer):
        r = analyzer._unary_result_type('~', IntegerType(kind=TypeKind.SHORT))
        assert r == IntegerType(kind=TypeKind.INT)

    def test_bitwise_not_long_stays_long(self, analyzer):
        r = analyzer._unary_result_type('~', IntegerType(kind=TypeKind.LONG))
        assert r == IntegerType(kind=TypeKind.LONG)

    # -- Unary plus (+) --

    def test_unary_plus_int(self, analyzer):
        r = analyzer._unary_result_type('+', IntegerType(kind=TypeKind.INT))
        assert r == IntegerType(kind=TypeKind.INT)

    def test_unary_plus_char_promotes_to_int(self, analyzer):
        r = analyzer._unary_result_type('+', IntegerType(kind=TypeKind.CHAR))
        assert r == IntegerType(kind=TypeKind.INT)

    def test_unary_plus_long_stays_long(self, analyzer):
        r = analyzer._unary_result_type('+', IntegerType(kind=TypeKind.LONG))
        assert r == IntegerType(kind=TypeKind.LONG)

    # -- Unary minus (-) --

    def test_unary_minus_int(self, analyzer):
        r = analyzer._unary_result_type('-', IntegerType(kind=TypeKind.INT))
        assert r == IntegerType(kind=TypeKind.INT)

    def test_unary_minus_char_promotes_to_int(self, analyzer):
        r = analyzer._unary_result_type('-', IntegerType(kind=TypeKind.CHAR))
        assert r == IntegerType(kind=TypeKind.INT)

    def test_unary_minus_short_promotes_to_int(self, analyzer):
        r = analyzer._unary_result_type('-', IntegerType(kind=TypeKind.SHORT))
        assert r == IntegerType(kind=TypeKind.INT)

    def test_unary_minus_long_stays_long(self, analyzer):
        r = analyzer._unary_result_type('-', IntegerType(kind=TypeKind.LONG))
        assert r == IntegerType(kind=TypeKind.LONG)

    # -- Increment/Decrement (++/--) --

    def test_prefix_increment_int(self, analyzer):
        operand = IntegerType(kind=TypeKind.INT)
        r = analyzer._unary_result_type('++', operand)
        assert r is operand

    def test_prefix_decrement_int(self, analyzer):
        operand = IntegerType(kind=TypeKind.INT)
        r = analyzer._unary_result_type('--', operand)
        assert r is operand

    def test_increment_pointer(self, analyzer):
        ptr = PointerType(kind=TypeKind.POINTER, pointee=IntegerType(kind=TypeKind.INT))
        r = analyzer._unary_result_type('++', ptr)
        assert r is ptr

    def test_decrement_pointer(self, analyzer):
        ptr = PointerType(kind=TypeKind.POINTER, pointee=IntegerType(kind=TypeKind.CHAR))
        r = analyzer._unary_result_type('--', ptr)
        assert r is ptr

    def test_increment_long(self, analyzer):
        operand = IntegerType(kind=TypeKind.LONG)
        r = analyzer._unary_result_type('++', operand)
        assert r is operand

    # -- Unknown operator --

    def test_unknown_op_returns_none(self, analyzer):
        r = analyzer._unary_result_type('???', IntegerType(kind=TypeKind.INT))
        assert r is None


class TestCastTypeAnnotation:
    """Tests for Cast expression type annotation (task 5.3)."""

    def test_cast_to_int(self, analyzer):
        from pycc.ast_nodes import Cast, FloatLiteral
        target_type = ASTType(line=1, column=1, base="int")
        inner = FloatLiteral(value=3.14, line=1, column=1)
        expr = Cast(line=1, column=1, type=target_type, expression=inner)
        analyzer._analyze_expr(expr)
        assert isinstance(expr.resolved_type, IntegerType)
        assert expr.resolved_type.kind == TypeKind.INT

    def test_cast_to_long(self, analyzer):
        from pycc.ast_nodes import Cast, IntLiteral
        target_type = ASTType(line=1, column=1, base="long")
        inner = IntLiteral(value=42, line=1, column=1)
        expr = Cast(line=1, column=1, type=target_type, expression=inner)
        analyzer._analyze_expr(expr)
        assert isinstance(expr.resolved_type, IntegerType)
        assert expr.resolved_type.kind == TypeKind.LONG

    def test_cast_to_pointer(self, analyzer):
        from pycc.ast_nodes import Cast, IntLiteral
        target_type = ASTType(line=1, column=1, base="void", is_pointer=True, pointer_level=1)
        inner = IntLiteral(value=0, line=1, column=1)
        expr = Cast(line=1, column=1, type=target_type, expression=inner)
        analyzer._analyze_expr(expr)
        assert isinstance(expr.resolved_type, PointerType)
        assert expr.resolved_type.kind == TypeKind.POINTER

    def test_cast_to_unsigned_int(self, analyzer):
        from pycc.ast_nodes import Cast, IntLiteral
        target_type = ASTType(line=1, column=1, base="int", is_unsigned=True)
        inner = IntLiteral(value=-1, line=1, column=1)
        expr = Cast(line=1, column=1, type=target_type, expression=inner)
        analyzer._analyze_expr(expr)
        assert isinstance(expr.resolved_type, IntegerType)
        assert expr.resolved_type.kind == TypeKind.INT
        assert expr.resolved_type.is_unsigned is True

    def test_cast_to_char(self, analyzer):
        from pycc.ast_nodes import Cast, IntLiteral
        target_type = ASTType(line=1, column=1, base="char")
        inner = IntLiteral(value=65, line=1, column=1)
        expr = Cast(line=1, column=1, type=target_type, expression=inner)
        analyzer._analyze_expr(expr)
        assert isinstance(expr.resolved_type, IntegerType)
        assert expr.resolved_type.kind == TypeKind.CHAR

    def test_cast_to_double(self, analyzer):
        from pycc.ast_nodes import Cast, IntLiteral
        target_type = ASTType(line=1, column=1, base="double")
        inner = IntLiteral(value=42, line=1, column=1)
        expr = Cast(line=1, column=1, type=target_type, expression=inner)
        analyzer._analyze_expr(expr)
        assert isinstance(expr.resolved_type, FloatType)
        assert expr.resolved_type.kind == TypeKind.DOUBLE

    def test_cast_with_typedef(self, analyzer):
        from pycc.ast_nodes import Cast, IntLiteral
        # Set up typedef: size_t -> unsigned long
        analyzer._typedefs = [{"size_t": ASTType(line=0, column=0, base="long", is_unsigned=True)}]
        target_type = ASTType(line=1, column=1, base="size_t")
        inner = IntLiteral(value=10, line=1, column=1)
        expr = Cast(line=1, column=1, type=target_type, expression=inner)
        analyzer._analyze_expr(expr)
        assert isinstance(expr.resolved_type, IntegerType)
        assert expr.resolved_type.kind == TypeKind.LONG
        assert expr.resolved_type.is_unsigned is True


class TestSizeOfTypeAnnotation:
    """Tests for SizeOf expression type annotation (task 5.4)."""

    def test_sizeof_type_returns_unsigned_long(self, analyzer):
        """sizeof(int) should have resolved_type = IntegerType(LONG, unsigned)."""
        from pycc.ast_nodes import SizeOf

        target_type = ASTType(line=1, column=1, base="int")
        expr = SizeOf(line=1, column=1, operand=None, type=target_type)
        analyzer._analyze_expr(expr)
        assert isinstance(expr.resolved_type, IntegerType)
        assert expr.resolved_type.kind == TypeKind.LONG
        assert expr.resolved_type.is_unsigned is True

    def test_sizeof_expr_returns_unsigned_long(self, analyzer):
        """sizeof(x) where x is an expression should have resolved_type = unsigned long."""
        from pycc.ast_nodes import SizeOf, IntLiteral

        operand = IntLiteral(value=42, line=1, column=1)
        expr = SizeOf(line=1, column=1, operand=operand, type=None)
        analyzer._analyze_expr(expr)
        assert isinstance(expr.resolved_type, IntegerType)
        assert expr.resolved_type.kind == TypeKind.LONG
        assert expr.resolved_type.is_unsigned is True

    def test_sizeof_struct_type_returns_unsigned_long(self, analyzer):
        """sizeof(struct foo) should have resolved_type = unsigned long."""
        from pycc.ast_nodes import SizeOf

        target_type = ASTType(line=1, column=1, base="struct foo")
        # Add a layout so _type_size doesn't fail
        class FakeLayout:
            size = 16
            alignment = 8
        analyzer._layouts = {"struct foo": FakeLayout()}
        expr = SizeOf(line=1, column=1, operand=None, type=target_type)
        analyzer._analyze_expr(expr)
        assert isinstance(expr.resolved_type, IntegerType)
        assert expr.resolved_type.kind == TypeKind.LONG
        assert expr.resolved_type.is_unsigned is True

    def test_sizeof_identifier_returns_unsigned_long(self, analyzer):
        """sizeof(variable) should have resolved_type = unsigned long."""
        from pycc.ast_nodes import SizeOf, Identifier

        # Declare a variable so sizeof doesn't reject it
        analyzer._decl_types = {"x": ASTType(line=1, column=1, base="int")}
        operand = Identifier(name="x", line=1, column=1)
        expr = SizeOf(line=1, column=1, operand=operand, type=None)
        analyzer._analyze_expr(expr)
        assert isinstance(expr.resolved_type, IntegerType)
        assert expr.resolved_type.kind == TypeKind.LONG
        assert expr.resolved_type.is_unsigned is True


class TestFunctionCallTypeAnnotation:
    """Tests for FunctionCall expression type annotation (task 5.5)."""

    def test_function_call_returns_int(self, analyzer):
        """A function declared as returning int should annotate the call with IntegerType(INT)."""
        from pycc.ast_nodes import FunctionCall, Identifier

        # Register function signature: int foo(void)
        ret_type = ASTType(line=0, column=0, base="int")
        analyzer._function_full_sig = {"foo": ([], ret_type)}
        analyzer._functions = {"foo"}

        expr = FunctionCall(
            function=Identifier(name="foo", line=1, column=1),
            arguments=[],
            line=1, column=1,
        )
        analyzer._analyze_expr(expr)
        assert isinstance(expr.resolved_type, IntegerType)
        assert expr.resolved_type.kind == TypeKind.INT

    def test_function_call_returns_pointer(self, analyzer):
        """A function returning char* should annotate the call with PointerType(CHAR)."""
        from pycc.ast_nodes import FunctionCall, Identifier

        ret_type = ASTType(line=0, column=0, base="char", is_pointer=True, pointer_level=1)
        analyzer._function_full_sig = {"get_str": ([], ret_type)}
        analyzer._functions = {"get_str"}

        expr = FunctionCall(
            function=Identifier(name="get_str", line=1, column=1),
            arguments=[],
            line=1, column=1,
        )
        analyzer._analyze_expr(expr)
        assert isinstance(expr.resolved_type, PointerType)
        assert expr.resolved_type.pointee.kind == TypeKind.CHAR

    def test_function_call_returns_double(self, analyzer):
        """A function returning double should annotate the call with FloatType(DOUBLE)."""
        from pycc.ast_nodes import FunctionCall, Identifier

        ret_type = ASTType(line=0, column=0, base="double")
        analyzer._function_full_sig = {"compute": ([], ret_type)}
        analyzer._functions = {"compute"}

        expr = FunctionCall(
            function=Identifier(name="compute", line=1, column=1),
            arguments=[],
            line=1, column=1,
        )
        analyzer._analyze_expr(expr)
        assert isinstance(expr.resolved_type, FloatType)
        assert expr.resolved_type.kind == TypeKind.DOUBLE

    def test_function_call_returns_long(self, analyzer):
        """A function returning long should annotate the call with IntegerType(LONG)."""
        from pycc.ast_nodes import FunctionCall, Identifier

        ret_type = ASTType(line=0, column=0, base="long")
        analyzer._function_full_sig = {"get_size": ([], ret_type)}
        analyzer._functions = {"get_size"}

        expr = FunctionCall(
            function=Identifier(name="get_size", line=1, column=1),
            arguments=[],
            line=1, column=1,
        )
        analyzer._analyze_expr(expr)
        assert isinstance(expr.resolved_type, IntegerType)
        assert expr.resolved_type.kind == TypeKind.LONG

    def test_function_call_implicit_int_for_undeclared(self, analyzer):
        """An undeclared function (C89 implicit declaration) should default to int return."""
        from pycc.ast_nodes import FunctionCall, Identifier

        # No signature registered - simulates implicit declaration
        analyzer._function_full_sig = {}
        analyzer._functions = set()

        expr = FunctionCall(
            function=Identifier(name="unknown_func", line=1, column=1),
            arguments=[],
            line=1, column=1,
        )
        analyzer._analyze_expr(expr)
        assert isinstance(expr.resolved_type, IntegerType)
        assert expr.resolved_type.kind == TypeKind.INT

    def test_function_call_with_arguments(self, analyzer):
        """Function call with arguments should still annotate return type correctly."""
        from pycc.ast_nodes import FunctionCall, Identifier, IntLiteral

        ret_type = ASTType(line=0, column=0, base="int")
        param_types = [ASTType(line=0, column=0, base="int")]
        analyzer._function_full_sig = {"add": (param_types, ret_type)}
        analyzer._functions = {"add"}
        analyzer._function_sigs = {"add": ("int", 1, False)}

        expr = FunctionCall(
            function=Identifier(name="add", line=1, column=1),
            arguments=[IntLiteral(value=5, line=1, column=5)],
            line=1, column=1,
        )
        analyzer._analyze_expr(expr)
        assert isinstance(expr.resolved_type, IntegerType)
        assert expr.resolved_type.kind == TypeKind.INT

    def test_function_call_returns_unsigned_int(self, analyzer):
        """A function returning unsigned int should annotate correctly."""
        from pycc.ast_nodes import FunctionCall, Identifier

        ret_type = ASTType(line=0, column=0, base="int", is_unsigned=True)
        analyzer._function_full_sig = {"get_count": ([], ret_type)}
        analyzer._functions = {"get_count"}

        expr = FunctionCall(
            function=Identifier(name="get_count", line=1, column=1),
            arguments=[],
            line=1, column=1,
        )
        analyzer._analyze_expr(expr)
        assert isinstance(expr.resolved_type, IntegerType)
        assert expr.resolved_type.kind == TypeKind.INT
        assert expr.resolved_type.is_unsigned is True

    def test_function_pointer_call_no_type_info(self, analyzer):
        """A function pointer call with no signature defaults to implicit int (C89)."""
        from pycc.ast_nodes import FunctionCall, Identifier

        # Simulate calling through a name that has no registered signature
        callee = Identifier(name="fptr", line=1, column=1)
        analyzer._decl_types = {
            "fptr": ASTType(line=0, column=0, base="int", is_pointer=True, pointer_level=1)
        }
        analyzer._function_full_sig = {}
        analyzer._functions = set()
        analyzer._function_sigs = {}

        expr = FunctionCall(
            function=callee,
            arguments=[],
            line=1, column=1,
        )
        analyzer._analyze_expr(expr)
        # fptr is an Identifier so it goes through the named function path
        # Without a signature, it defaults to implicit int (C89)
        assert isinstance(expr.resolved_type, IntegerType)
        assert expr.resolved_type.kind == TypeKind.INT


class TestTernaryOpTypeAnnotation:
    """Tests for TernaryOp expression type annotation (task 6.1)."""

    def test_ternary_both_int(self, analyzer):
        """Both branches are int: result should be int."""
        from pycc.ast_nodes import TernaryOp, IntLiteral

        expr = TernaryOp(
            condition=IntLiteral(value=1, line=1, column=1),
            true_expr=IntLiteral(value=10, line=1, column=5),
            false_expr=IntLiteral(value=20, line=1, column=9),
            line=1, column=1,
        )
        analyzer._analyze_expr(expr)
        assert isinstance(expr.resolved_type, IntegerType)
        assert expr.resolved_type.kind == TypeKind.INT

    def test_ternary_int_and_double_uac(self, analyzer):
        """int and double branches: UAC should produce double."""
        from pycc.ast_nodes import TernaryOp, IntLiteral, FloatLiteral

        expr = TernaryOp(
            condition=IntLiteral(value=1, line=1, column=1),
            true_expr=IntLiteral(value=10, line=1, column=5),
            false_expr=FloatLiteral(value=3.14, line=1, column=9),
            line=1, column=1,
        )
        analyzer._analyze_expr(expr)
        assert isinstance(expr.resolved_type, FloatType)
        assert expr.resolved_type.kind == TypeKind.DOUBLE

    def test_ternary_float_and_double_uac(self, analyzer):
        """float and double branches: UAC should produce double."""
        from pycc.ast_nodes import TernaryOp, FloatLiteral, IntLiteral

        expr = TernaryOp(
            condition=IntLiteral(value=1, line=1, column=1),
            true_expr=FloatLiteral(value=1.0, suffix='f', line=1, column=5),
            false_expr=FloatLiteral(value=2.0, line=1, column=9),
            line=1, column=1,
        )
        analyzer._analyze_expr(expr)
        assert isinstance(expr.resolved_type, FloatType)
        assert expr.resolved_type.kind == TypeKind.DOUBLE

    def test_ternary_both_pointers(self, analyzer):
        """Both branches are pointers: result should be pointer type."""
        from pycc.ast_nodes import TernaryOp, IntLiteral, Identifier

        # Set up two pointer variables
        analyzer._decl_types = {
            "p": ASTType(line=0, column=0, base="int", is_pointer=True, pointer_level=1),
            "q": ASTType(line=0, column=0, base="int", is_pointer=True, pointer_level=1),
        }

        expr = TernaryOp(
            condition=IntLiteral(value=1, line=1, column=1),
            true_expr=Identifier(name="p", line=1, column=5),
            false_expr=Identifier(name="q", line=1, column=9),
            line=1, column=1,
        )
        analyzer._analyze_expr(expr)
        assert isinstance(expr.resolved_type, PointerType)
        assert expr.resolved_type.pointee.kind == TypeKind.INT

    def test_ternary_pointer_and_null(self, analyzer):
        """One branch is pointer, other is NULL (0): result should be pointer type."""
        from pycc.ast_nodes import TernaryOp, IntLiteral, Identifier

        analyzer._decl_types = {
            "p": ASTType(line=0, column=0, base="char", is_pointer=True, pointer_level=1),
        }

        expr = TernaryOp(
            condition=IntLiteral(value=1, line=1, column=1),
            true_expr=Identifier(name="p", line=1, column=5),
            false_expr=IntLiteral(value=0, line=1, column=9),
            line=1, column=1,
        )
        analyzer._analyze_expr(expr)
        assert isinstance(expr.resolved_type, PointerType)
        assert expr.resolved_type.pointee.kind == TypeKind.CHAR

    def test_ternary_null_and_pointer(self, analyzer):
        """NULL (0) in true branch, pointer in false branch: result should be pointer type."""
        from pycc.ast_nodes import TernaryOp, IntLiteral, Identifier

        analyzer._decl_types = {
            "p": ASTType(line=0, column=0, base="int", is_pointer=True, pointer_level=1),
        }

        expr = TernaryOp(
            condition=IntLiteral(value=0, line=1, column=1),
            true_expr=IntLiteral(value=0, line=1, column=5),
            false_expr=Identifier(name="p", line=1, column=9),
            line=1, column=1,
        )
        analyzer._analyze_expr(expr)
        assert isinstance(expr.resolved_type, PointerType)
        assert expr.resolved_type.pointee.kind == TypeKind.INT

    def test_ternary_char_and_int_promotes(self, analyzer):
        """char and int branches: integer promotion then UAC gives int."""
        from pycc.ast_nodes import TernaryOp, IntLiteral, CharLiteral

        expr = TernaryOp(
            condition=IntLiteral(value=1, line=1, column=1),
            true_expr=CharLiteral(value='a', line=1, column=5),
            false_expr=IntLiteral(value=42, line=1, column=9),
            line=1, column=1,
        )
        analyzer._analyze_expr(expr)
        assert isinstance(expr.resolved_type, IntegerType)
        assert expr.resolved_type.kind == TypeKind.INT

    def test_ternary_one_branch_unknown(self, analyzer):
        """If one branch has no resolved_type, use the other branch's type."""
        from pycc.ast_nodes import TernaryOp, IntLiteral, Identifier

        # unknown_var is not declared, so its resolved_type will be None
        expr = TernaryOp(
            condition=IntLiteral(value=1, line=1, column=1),
            true_expr=IntLiteral(value=10, line=1, column=5),
            false_expr=Identifier(name="unknown_var", line=1, column=9),
            line=1, column=1,
        )
        analyzer._analyze_expr(expr)
        assert isinstance(expr.resolved_type, IntegerType)
        assert expr.resolved_type.kind == TypeKind.INT
