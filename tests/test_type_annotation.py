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
