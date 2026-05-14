"""Unit tests for IRGenerator CType query helper functions.

Tests _operand_ctype, _is_unsigned_operand, _is_pointer_operand,
_is_array_operand, _is_struct_operand, _is_float_operand.
"""

import pytest
from pycc.types import (
    CType, TypeKind, IntegerType, FloatType, PointerType,
    ArrayType, StructType, TypedSymbolTable, Qualifiers,
)
from pycc.ir import IRGenerator


@pytest.fixture
def ir_gen():
    """Create a minimal IRGenerator with a TypedSymbolTable."""
    gen = IRGenerator.__new__(IRGenerator)
    gen._sym_table = TypedSymbolTable()
    gen._var_types = {}
    gen._sema_ctx = None
    return gen


class TestOperandCtype:
    """Tests for _operand_ctype unified query."""

    def test_returns_ctype_from_sym_table(self, ir_gen):
        ct = IntegerType(kind=TypeKind.INT)
        ir_gen._sym_table.insert("%t0", ct)
        result = ir_gen._operand_ctype("%t0")
        assert result is ct

    def test_fallback_to_var_types(self, ir_gen):
        ir_gen._var_types["@x"] = "unsigned long"
        result = ir_gen._operand_ctype("@x")
        assert result is not None
        assert result.kind == TypeKind.LONG
        assert result.is_unsigned is True

    def test_returns_none_for_unknown(self, ir_gen):
        result = ir_gen._operand_ctype("%t99")
        assert result is None

    def test_sym_table_takes_priority(self, ir_gen):
        ct = FloatType(kind=TypeKind.FLOAT)
        ir_gen._sym_table.insert("%t0", ct)
        ir_gen._var_types["%t0"] = "int"
        result = ir_gen._operand_ctype("%t0")
        assert result.kind == TypeKind.FLOAT


class TestIsUnsignedOperand:
    """Tests for _is_unsigned_operand."""

    def test_unsigned_int_from_sym_table(self, ir_gen):
        ct = IntegerType(kind=TypeKind.INT, is_unsigned=True)
        ir_gen._sym_table.insert("%t0", ct)
        assert ir_gen._is_unsigned_operand("%t0") is True

    def test_signed_int_from_sym_table(self, ir_gen):
        ct = IntegerType(kind=TypeKind.INT, is_unsigned=False)
        ir_gen._sym_table.insert("%t0", ct)
        assert ir_gen._is_unsigned_operand("%t0") is False

    def test_non_integer_returns_false(self, ir_gen):
        ct = FloatType(kind=TypeKind.FLOAT)
        ir_gen._sym_table.insert("%t0", ct)
        assert ir_gen._is_unsigned_operand("%t0") is False

    def test_fallback_unsigned_string(self, ir_gen):
        ir_gen._sym_table = None
        ir_gen._var_types["%t0"] = "unsigned int"
        assert ir_gen._is_unsigned_operand("%t0") is True

    def test_fallback_signed_string(self, ir_gen):
        ir_gen._sym_table = None
        ir_gen._var_types["%t0"] = "int"
        assert ir_gen._is_unsigned_operand("%t0") is False

    def test_non_string_op_returns_false(self, ir_gen):
        assert ir_gen._is_unsigned_operand(None) is False
        assert ir_gen._is_unsigned_operand(42) is False


class TestIsPointerOperand:
    """Tests for _is_pointer_operand."""

    def test_pointer_from_sym_table(self, ir_gen):
        ct = PointerType(kind=TypeKind.POINTER, pointee=IntegerType(kind=TypeKind.INT))
        ir_gen._sym_table.insert("@p", ct)
        assert ir_gen._is_pointer_operand("@p") is True

    def test_non_pointer_from_sym_table(self, ir_gen):
        ct = IntegerType(kind=TypeKind.INT)
        ir_gen._sym_table.insert("@x", ct)
        assert ir_gen._is_pointer_operand("@x") is False

    def test_fallback_pointer_string(self, ir_gen):
        ir_gen._sym_table = None
        ir_gen._var_types["@p"] = "int*"
        assert ir_gen._is_pointer_operand("@p") is True

    def test_fallback_non_pointer_string(self, ir_gen):
        ir_gen._sym_table = None
        ir_gen._var_types["@x"] = "int"
        assert ir_gen._is_pointer_operand("@x") is False


class TestIsArrayOperand:
    """Tests for _is_array_operand."""

    def test_array_from_sym_table(self, ir_gen):
        ct = ArrayType(kind=TypeKind.ARRAY, element=IntegerType(kind=TypeKind.INT), size=10)
        ir_gen._sym_table.insert("@arr", ct)
        assert ir_gen._is_array_operand("@arr") is True

    def test_non_array_from_sym_table(self, ir_gen):
        ct = IntegerType(kind=TypeKind.INT)
        ir_gen._sym_table.insert("@x", ct)
        assert ir_gen._is_array_operand("@x") is False

    def test_fallback_array_string(self, ir_gen):
        ir_gen._sym_table = None
        ir_gen._var_types["@arr"] = "array(char,$4)"
        assert ir_gen._is_array_operand("@arr") is True

    def test_fallback_non_array_string(self, ir_gen):
        ir_gen._sym_table = None
        ir_gen._var_types["@x"] = "int"
        assert ir_gen._is_array_operand("@x") is False


class TestIsStructOperand:
    """Tests for _is_struct_operand."""

    def test_struct_from_sym_table(self, ir_gen):
        ct = StructType(kind=TypeKind.STRUCT, tag="Foo")
        ir_gen._sym_table.insert("@s", ct)
        assert ir_gen._is_struct_operand("@s") is True

    def test_union_from_sym_table(self, ir_gen):
        ct = StructType(kind=TypeKind.UNION, tag="Bar")
        ir_gen._sym_table.insert("@u", ct)
        assert ir_gen._is_struct_operand("@u") is True

    def test_non_struct_from_sym_table(self, ir_gen):
        ct = IntegerType(kind=TypeKind.INT)
        ir_gen._sym_table.insert("@x", ct)
        assert ir_gen._is_struct_operand("@x") is False

    def test_fallback_struct_string(self, ir_gen):
        ir_gen._sym_table = None
        ir_gen._var_types["@s"] = "struct Foo"
        assert ir_gen._is_struct_operand("@s") is True

    def test_fallback_union_string(self, ir_gen):
        ir_gen._sym_table = None
        ir_gen._var_types["@u"] = "union Bar"
        assert ir_gen._is_struct_operand("@u") is True

    def test_fallback_non_struct_string(self, ir_gen):
        ir_gen._sym_table = None
        ir_gen._var_types["@x"] = "int"
        assert ir_gen._is_struct_operand("@x") is False


class TestIsFloatOperand:
    """Tests for _is_float_operand."""

    def test_float_from_sym_table(self, ir_gen):
        ct = FloatType(kind=TypeKind.FLOAT)
        ir_gen._sym_table.insert("%t0", ct)
        assert ir_gen._is_float_operand("%t0") is True

    def test_double_from_sym_table(self, ir_gen):
        ct = FloatType(kind=TypeKind.DOUBLE)
        ir_gen._sym_table.insert("%t0", ct)
        assert ir_gen._is_float_operand("%t0") is True

    def test_non_float_from_sym_table(self, ir_gen):
        ct = IntegerType(kind=TypeKind.INT)
        ir_gen._sym_table.insert("%t0", ct)
        assert ir_gen._is_float_operand("%t0") is False

    def test_fallback_float_string(self, ir_gen):
        ir_gen._sym_table = None
        ir_gen._var_types["%t0"] = "float"
        assert ir_gen._is_float_operand("%t0") is True

    def test_fallback_double_string(self, ir_gen):
        ir_gen._sym_table = None
        ir_gen._var_types["%t0"] = "double"
        assert ir_gen._is_float_operand("%t0") is True

    def test_fallback_non_float_string(self, ir_gen):
        ir_gen._sym_table = None
        ir_gen._var_types["%t0"] = "int"
        assert ir_gen._is_float_operand("%t0") is False


class TestSymTablePriority:
    """Tests verifying _sym_table takes priority over _var_types."""

    def test_sym_table_overrides_var_types_unsigned(self, ir_gen):
        ir_gen._sym_table.insert("%t0", IntegerType(kind=TypeKind.INT, is_unsigned=False))
        ir_gen._var_types["%t0"] = "unsigned int"
        assert ir_gen._is_unsigned_operand("%t0") is False

    def test_sym_table_overrides_var_types_pointer(self, ir_gen):
        ir_gen._sym_table.insert("@p", IntegerType(kind=TypeKind.INT))
        ir_gen._var_types["@p"] = "int*"
        assert ir_gen._is_pointer_operand("@p") is False

    def test_sym_table_overrides_var_types_float(self, ir_gen):
        ir_gen._sym_table.insert("%t0", IntegerType(kind=TypeKind.INT))
        ir_gen._var_types["%t0"] = "float"
        assert ir_gen._is_float_operand("%t0") is False
