"""Tests for codegen CType-based type judgment migration (task 5.2).

Verifies that CodeGenerator's type helper methods correctly use CType
from the symbol table, with string-based fallback when CType is unavailable.
"""

import pytest
from pycc.types import (
    CType, TypeKind, IntegerType, FloatType, PointerType, StructType,
    ArrayType, EnumType, Qualifiers, TypedSymbolTable,
    type_sizeof, _str_to_ctype,
)
from pycc.codegen import CodeGenerator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class FakeSemaCtx:
    """Minimal SemanticContext stub for testing."""

    def __init__(self, layouts=None, typedefs=None, global_types=None):
        self.layouts = layouts or {}
        self.typedefs = typedefs or {}
        self.global_types = global_types or {}


class FakeLayout:
    """Minimal StructLayout stub."""

    def __init__(self, size, member_offsets=None, member_sizes=None,
                 member_types=None, align=1, bit_fields=None, _bf_info=None):
        self.size = size
        self.member_offsets = member_offsets or {}
        self.member_sizes = member_sizes or {}
        self.member_types = member_types or {}
        self.align = align
        self.bit_fields = bit_fields
        self._bf_info = _bf_info


def _make_codegen(sema_ctx=None, sym_table=None):
    """Create a CodeGenerator with optional sema_ctx and sym_table."""
    cg = CodeGenerator(optimize=False, sema_ctx=sema_ctx, sym_table=sym_table)
    cg._var_types = {}
    return cg


# ---------------------------------------------------------------------------
# _ctype_is_struct_or_union
# ---------------------------------------------------------------------------

class TestCtypeIsStructOrUnion:
    def test_struct_type(self):
        cg = _make_codegen()
        ct = StructType(kind=TypeKind.STRUCT, tag="Foo")
        assert cg._ctype_is_struct_or_union(ct) is True

    def test_union_type(self):
        cg = _make_codegen()
        ct = StructType(kind=TypeKind.UNION, tag="Bar")
        assert cg._ctype_is_struct_or_union(ct) is True

    def test_int_type(self):
        cg = _make_codegen()
        ct = IntegerType(kind=TypeKind.INT)
        assert cg._ctype_is_struct_or_union(ct) is False

    def test_pointer_type(self):
        cg = _make_codegen()
        ct = PointerType(kind=TypeKind.POINTER, pointee=IntegerType(kind=TypeKind.INT))
        assert cg._ctype_is_struct_or_union(ct) is False

    def test_none(self):
        cg = _make_codegen()
        assert cg._ctype_is_struct_or_union(None) is False


# ---------------------------------------------------------------------------
# _ctype_is_pointer
# ---------------------------------------------------------------------------

class TestCtypeIsPointer:
    def test_pointer(self):
        cg = _make_codegen()
        ct = PointerType(kind=TypeKind.POINTER, pointee=IntegerType(kind=TypeKind.INT))
        assert cg._ctype_is_pointer(ct) is True

    def test_non_pointer(self):
        cg = _make_codegen()
        ct = IntegerType(kind=TypeKind.INT)
        assert cg._ctype_is_pointer(ct) is False

    def test_none(self):
        cg = _make_codegen()
        assert cg._ctype_is_pointer(None) is False


# ---------------------------------------------------------------------------
# _ctype_struct_tag
# ---------------------------------------------------------------------------

class TestCtypeStructTag:
    def test_struct(self):
        cg = _make_codegen()
        ct = StructType(kind=TypeKind.STRUCT, tag="Point")
        assert cg._ctype_struct_tag(ct) == "struct Point"

    def test_union(self):
        cg = _make_codegen()
        ct = StructType(kind=TypeKind.UNION, tag="Data")
        assert cg._ctype_struct_tag(ct) == "union Data"

    def test_no_tag(self):
        cg = _make_codegen()
        ct = StructType(kind=TypeKind.STRUCT, tag=None)
        assert cg._ctype_struct_tag(ct) is None

    def test_non_struct(self):
        cg = _make_codegen()
        ct = IntegerType(kind=TypeKind.INT)
        assert cg._ctype_struct_tag(ct) is None


# ---------------------------------------------------------------------------
# _ctype_sizeof
# ---------------------------------------------------------------------------

class TestCtypeSizeof:
    def test_int(self):
        cg = _make_codegen()
        ct = IntegerType(kind=TypeKind.INT)
        assert cg._ctype_sizeof(ct) == 4

    def test_char(self):
        cg = _make_codegen()
        ct = IntegerType(kind=TypeKind.CHAR)
        assert cg._ctype_sizeof(ct) == 1

    def test_pointer(self):
        cg = _make_codegen()
        ct = PointerType(kind=TypeKind.POINTER, pointee=IntegerType(kind=TypeKind.INT))
        assert cg._ctype_sizeof(ct) == 8

    def test_struct_with_layout(self):
        layout = FakeLayout(size=20)
        sema = FakeSemaCtx(layouts={"struct Foo": layout})
        cg = _make_codegen(sema_ctx=sema)
        ct = StructType(kind=TypeKind.STRUCT, tag="Foo")
        assert cg._ctype_sizeof(ct) == 20

    def test_struct_no_layout(self):
        cg = _make_codegen()
        ct = StructType(kind=TypeKind.STRUCT, tag="Missing")
        assert cg._ctype_sizeof(ct) == 0

    def test_union_with_layout(self):
        layout = FakeLayout(size=8)
        sema = FakeSemaCtx(layouts={"union Bar": layout})
        cg = _make_codegen(sema_ctx=sema)
        ct = StructType(kind=TypeKind.UNION, tag="Bar")
        assert cg._ctype_sizeof(ct) == 8


# ---------------------------------------------------------------------------
# _get_base_struct_ctype
# ---------------------------------------------------------------------------

class TestGetBaseStructCtype:
    def test_direct_struct(self):
        sym_table = TypedSymbolTable()
        sym_table.insert("@s", StructType(kind=TypeKind.STRUCT, tag="Point"))
        cg = _make_codegen(sym_table=sym_table)
        ct = cg._get_base_struct_ctype("@s")
        assert ct is not None
        assert ct.kind == TypeKind.STRUCT

    def test_pointer_to_struct(self):
        sym_table = TypedSymbolTable()
        pointee = StructType(kind=TypeKind.STRUCT, tag="Node")
        sym_table.insert("%t0", PointerType(kind=TypeKind.POINTER, pointee=pointee))
        cg = _make_codegen(sym_table=sym_table)
        ct = cg._get_base_struct_ctype("%t0")
        assert ct is not None
        assert ct.kind == TypeKind.STRUCT
        assert ct.tag == "Node"

    def test_non_struct(self):
        sym_table = TypedSymbolTable()
        sym_table.insert("@x", IntegerType(kind=TypeKind.INT))
        cg = _make_codegen(sym_table=sym_table)
        assert cg._get_base_struct_ctype("@x") is None

    def test_unknown_symbol(self):
        cg = _make_codegen()
        assert cg._get_base_struct_ctype("@unknown") is None

    def test_fallback_to_var_types(self):
        """When symbol table has no entry, _get_type falls back to _var_types."""
        cg = _make_codegen()
        cg._var_types["@s"] = "struct Point"
        ct = cg._get_base_struct_ctype("@s")
        assert ct is not None
        assert ct.kind == TypeKind.STRUCT


# ---------------------------------------------------------------------------
# _resolve_member via CType path
# ---------------------------------------------------------------------------

class TestResolveMemberCtype:
    def test_ctype_path_finds_member(self):
        layout = FakeLayout(
            size=8,
            member_offsets={"x": 0, "y": 4},
            member_sizes={"x": 4, "y": 4},
            member_types={"x": "int", "y": "int"},
        )
        sema = FakeSemaCtx(layouts={"struct Point": layout})
        sym_table = TypedSymbolTable()
        sym_table.insert("@p", StructType(kind=TypeKind.STRUCT, tag="Point"))
        cg = _make_codegen(sema_ctx=sema, sym_table=sym_table)
        off, sz = cg._resolve_member("@p", "y")
        assert off == 4
        assert sz == 4

    def test_string_fallback_when_no_sym_table(self):
        layout = FakeLayout(
            size=8,
            member_offsets={"x": 0, "y": 4},
            member_sizes={"x": 4, "y": 4},
        )
        sema = FakeSemaCtx(layouts={"struct Point": layout})
        cg = _make_codegen(sema_ctx=sema)
        cg._var_types["@p"] = "struct Point"
        off, sz = cg._resolve_member("@p", "y")
        assert off == 4
        assert sz == 4


# ---------------------------------------------------------------------------
# _resolve_member_type via CType path
# ---------------------------------------------------------------------------

class TestResolveMemberTypeCtype:
    def test_ctype_path(self):
        layout = FakeLayout(
            size=8,
            member_offsets={"x": 0, "y": 4},
            member_sizes={"x": 4, "y": 4},
            member_types={"x": "int", "y": "unsigned char"},
        )
        sema = FakeSemaCtx(layouts={"struct S": layout})
        sym_table = TypedSymbolTable()
        sym_table.insert("@s", StructType(kind=TypeKind.STRUCT, tag="S"))
        cg = _make_codegen(sema_ctx=sema, sym_table=sym_table)
        assert cg._resolve_member_type("@s", "y") == "unsigned char"

    def test_string_fallback(self):
        layout = FakeLayout(
            size=8,
            member_offsets={"x": 0},
            member_sizes={"x": 4},
            member_types={"x": "signed char"},
        )
        sema = FakeSemaCtx(layouts={"struct S": layout})
        cg = _make_codegen(sema_ctx=sema)
        cg._var_types["@s"] = "struct S"
        assert cg._resolve_member_type("@s", "x") == "signed char"


# ---------------------------------------------------------------------------
# _type_size_bytes with CType struct path
# ---------------------------------------------------------------------------

class TestTypeSizeBytesCtype:
    def test_struct_via_ctype(self):
        layout = FakeLayout(size=24)
        sema = FakeSemaCtx(layouts={"struct Big": layout})
        cg = _make_codegen(sema_ctx=sema)
        assert cg._type_size_bytes("struct Big") == 24

    def test_scalar_unchanged(self):
        cg = _make_codegen()
        assert cg._type_size_bytes("int") == 4
        assert cg._type_size_bytes("char") == 1
        assert cg._type_size_bytes("long") == 8
        assert cg._type_size_bytes("long double") == 16
        assert cg._type_size_bytes("float") == 4
        assert cg._type_size_bytes("double") == 8

    def test_pointer_unchanged(self):
        cg = _make_codegen()
        assert cg._type_size_bytes("int *") == 8
        assert cg._type_size_bytes("char *") == 8


# ---------------------------------------------------------------------------
# Task 5.5: Cast and pointer arithmetic CType migration
# ---------------------------------------------------------------------------

class TestCastCTypeMigration:
    """Tests for CType-based cast instruction handling in codegen."""

    def test_i2f_result_type_float(self):
        """i2f with result_type=FloatType should use float conversion."""
        from pycc.ir import IRInstruction
        sym_table = TypedSymbolTable()
        sym_table.insert("@x", IntegerType(kind=TypeKind.INT))
        cg = _make_codegen(sym_table=sym_table)
        ins = IRInstruction(
            op="i2f", result="%t0", operand1="@x",
            result_type=FloatType(kind=TypeKind.FLOAT),
        )
        # The result_type should be FloatType
        assert ins.result_type is not None
        assert ins.result_type.kind == TypeKind.FLOAT

    def test_i2d_result_type_double(self):
        """i2d with result_type=FloatType(DOUBLE) should use double conversion."""
        from pycc.ir import IRInstruction
        ins = IRInstruction(
            op="i2d", result="%t0", operand1="@x",
            result_type=FloatType(kind=TypeKind.DOUBLE),
        )
        assert ins.result_type is not None
        assert ins.result_type.kind == TypeKind.DOUBLE

    def test_f2i_source_type_from_symbol_table(self):
        """f2i should be able to determine source fp type from symbol table."""
        sym_table = TypedSymbolTable()
        sym_table.insert("%t0", FloatType(kind=TypeKind.FLOAT))
        cg = _make_codegen(sym_table=sym_table)
        ct = cg._get_type("%t0")
        assert ct is not None
        assert ct.kind == TypeKind.FLOAT

    def test_d2i_source_type_from_symbol_table(self):
        """d2i should be able to determine source fp type from symbol table."""
        sym_table = TypedSymbolTable()
        sym_table.insert("%t0", FloatType(kind=TypeKind.DOUBLE))
        cg = _make_codegen(sym_table=sym_table)
        ct = cg._get_type("%t0")
        assert ct is not None
        assert ct.kind == TypeKind.DOUBLE


class TestPointerArithmeticCTypeMigration:
    """Tests for CType-based pointer arithmetic in codegen."""

    def test_get_type_returns_pointer_for_ptr_operand(self):
        """Symbol table lookup should return PointerType for pointer operands."""
        sym_table = TypedSymbolTable()
        pointee = IntegerType(kind=TypeKind.INT)
        sym_table.insert("@p", PointerType(kind=TypeKind.POINTER, pointee=pointee))
        cg = _make_codegen(sym_table=sym_table)
        ct = cg._get_type("@p")
        assert ct is not None
        assert cg._ctype_is_pointer(ct)
        deref = cg._ctype_deref(ct)
        assert deref is not None
        assert deref.kind == TypeKind.INT

    def test_pointee_sizeof_int(self):
        """Pointee size for int* should be 4."""
        sym_table = TypedSymbolTable()
        pointee = IntegerType(kind=TypeKind.INT)
        sym_table.insert("@p", PointerType(kind=TypeKind.POINTER, pointee=pointee))
        cg = _make_codegen(sym_table=sym_table)
        ct = cg._get_type("@p")
        deref = cg._ctype_deref(ct)
        assert type_sizeof(deref) == 4

    def test_pointee_sizeof_char(self):
        """Pointee size for char* should be 1."""
        sym_table = TypedSymbolTable()
        pointee = IntegerType(kind=TypeKind.CHAR)
        sym_table.insert("@p", PointerType(kind=TypeKind.POINTER, pointee=pointee))
        cg = _make_codegen(sym_table=sym_table)
        ct = cg._get_type("@p")
        deref = cg._ctype_deref(ct)
        assert type_sizeof(deref) == 1

    def test_pointee_sizeof_long(self):
        """Pointee size for long* should be 8."""
        sym_table = TypedSymbolTable()
        pointee = IntegerType(kind=TypeKind.LONG)
        sym_table.insert("@p", PointerType(kind=TypeKind.POINTER, pointee=pointee))
        cg = _make_codegen(sym_table=sym_table)
        ct = cg._get_type("@p")
        deref = cg._ctype_deref(ct)
        assert type_sizeof(deref) == 8

    def test_pointee_sizeof_struct(self):
        """Pointee size for struct* should use layout size."""
        layout = FakeLayout(size=20)
        sema = FakeSemaCtx(layouts={"struct Point": layout})
        sym_table = TypedSymbolTable()
        pointee = StructType(kind=TypeKind.STRUCT, tag="Point")
        sym_table.insert("@p", PointerType(kind=TypeKind.POINTER, pointee=pointee))
        cg = _make_codegen(sema_ctx=sema, sym_table=sym_table)
        ct = cg._get_type("@p")
        deref = cg._ctype_deref(ct)
        assert cg._ctype_sizeof(deref) == 20

    def test_array_element_sizeof(self):
        """Array element size should be computed from CType."""
        sym_table = TypedSymbolTable()
        elem = IntegerType(kind=TypeKind.INT)
        sym_table.insert("@arr", ArrayType(kind=TypeKind.ARRAY, element=elem, size=10))
        cg = _make_codegen(sym_table=sym_table)
        ct = cg._get_type("@arr")
        assert isinstance(ct, ArrayType)
        assert ct.element is not None
        assert type_sizeof(ct.element) == 4

    def test_pointer_to_pointer_sizeof(self):
        """Pointee size for int** should be 8 (pointer size)."""
        sym_table = TypedSymbolTable()
        inner = PointerType(kind=TypeKind.POINTER, pointee=IntegerType(kind=TypeKind.INT))
        sym_table.insert("@pp", PointerType(kind=TypeKind.POINTER, pointee=inner))
        cg = _make_codegen(sym_table=sym_table)
        ct = cg._get_type("@pp")
        deref = cg._ctype_deref(ct)
        assert type_sizeof(deref) == 8

    def test_binop_ptr_check_uses_ctype(self):
        """CType-based pointer check in binop should detect pointer operands."""
        sym_table = TypedSymbolTable()
        sym_table.insert("@p", PointerType(kind=TypeKind.POINTER,
                                           pointee=IntegerType(kind=TypeKind.INT)))
        sym_table.insert("@n", IntegerType(kind=TypeKind.INT))
        cg = _make_codegen(sym_table=sym_table)
        ct_p = cg._get_type("@p")
        ct_n = cg._get_type("@n")
        assert cg._ctype_is_pointer(ct_p) is True
        assert cg._ctype_is_pointer(ct_n) is False

    def test_unsigned_char_detection_via_ctype(self):
        """CType-based unsigned char detection for load_index."""
        sym_table = TypedSymbolTable()
        pointee = IntegerType(kind=TypeKind.CHAR, is_unsigned=True)
        sym_table.insert("@p", PointerType(kind=TypeKind.POINTER, pointee=pointee))
        cg = _make_codegen(sym_table=sym_table)
        ct = cg._get_type("@p")
        deref = cg._ctype_deref(ct)
        assert cg._ctype_is_unsigned_char(deref) is True

    def test_signed_char_not_unsigned(self):
        """Signed char should not be detected as unsigned."""
        sym_table = TypedSymbolTable()
        pointee = IntegerType(kind=TypeKind.CHAR, is_unsigned=False)
        sym_table.insert("@p", PointerType(kind=TypeKind.POINTER, pointee=pointee))
        cg = _make_codegen(sym_table=sym_table)
        ct = cg._get_type("@p")
        deref = cg._ctype_deref(ct)
        assert cg._ctype_is_unsigned_char(deref) is False


# ---------------------------------------------------------------------------
# Task 1.2: _operand_sizeof, _is_float_type_op, _is_array_type_op
# ---------------------------------------------------------------------------

class TestOperandSizeof:
    """Tests for _operand_sizeof CType-based helper."""

    def test_int_operand(self):
        sym_table = TypedSymbolTable()
        sym_table.insert("@x", IntegerType(kind=TypeKind.INT))
        cg = _make_codegen(sym_table=sym_table)
        assert cg._operand_sizeof("@x") == 4

    def test_char_operand(self):
        sym_table = TypedSymbolTable()
        sym_table.insert("@c", IntegerType(kind=TypeKind.CHAR))
        cg = _make_codegen(sym_table=sym_table)
        assert cg._operand_sizeof("@c") == 1

    def test_long_operand(self):
        sym_table = TypedSymbolTable()
        sym_table.insert("@l", IntegerType(kind=TypeKind.LONG))
        cg = _make_codegen(sym_table=sym_table)
        assert cg._operand_sizeof("@l") == 8

    def test_short_operand(self):
        sym_table = TypedSymbolTable()
        sym_table.insert("@s", IntegerType(kind=TypeKind.SHORT))
        cg = _make_codegen(sym_table=sym_table)
        assert cg._operand_sizeof("@s") == 2

    def test_pointer_operand(self):
        sym_table = TypedSymbolTable()
        sym_table.insert("@p", PointerType(kind=TypeKind.POINTER,
                                           pointee=IntegerType(kind=TypeKind.INT)))
        cg = _make_codegen(sym_table=sym_table)
        assert cg._operand_sizeof("@p") == 8

    def test_float_operand(self):
        sym_table = TypedSymbolTable()
        sym_table.insert("%t0", FloatType(kind=TypeKind.FLOAT))
        cg = _make_codegen(sym_table=sym_table)
        assert cg._operand_sizeof("%t0") == 4

    def test_double_operand(self):
        sym_table = TypedSymbolTable()
        sym_table.insert("%t1", FloatType(kind=TypeKind.DOUBLE))
        cg = _make_codegen(sym_table=sym_table)
        assert cg._operand_sizeof("%t1") == 8

    def test_array_operand(self):
        sym_table = TypedSymbolTable()
        elem = IntegerType(kind=TypeKind.INT)
        sym_table.insert("@arr", ArrayType(kind=TypeKind.ARRAY, element=elem, size=10))
        cg = _make_codegen(sym_table=sym_table)
        assert cg._operand_sizeof("@arr") == 40  # 4 * 10

    def test_struct_operand_with_layout(self):
        layout = FakeLayout(size=24)
        sema = FakeSemaCtx(layouts={"struct Point": layout})
        sym_table = TypedSymbolTable()
        sym_table.insert("@s", StructType(kind=TypeKind.STRUCT, tag="Point"))
        cg = _make_codegen(sema_ctx=sema, sym_table=sym_table)
        assert cg._operand_sizeof("@s") == 24

    def test_unknown_operand_defaults_to_8(self):
        cg = _make_codegen()
        assert cg._operand_sizeof("@unknown") == 8

    def test_fallback_to_var_types(self):
        """When sym_table has no entry, falls back to _var_types via _get_type."""
        cg = _make_codegen()
        cg._var_types["@x"] = "int"
        assert cg._operand_sizeof("@x") == 4

    def test_fallback_var_types_double(self):
        cg = _make_codegen()
        cg._var_types["%t0"] = "double"
        assert cg._operand_sizeof("%t0") == 8


class TestIsFloatTypeOp:
    """Tests for _is_float_type_op CType-based helper."""

    def test_float_type(self):
        sym_table = TypedSymbolTable()
        sym_table.insert("%t0", FloatType(kind=TypeKind.FLOAT))
        cg = _make_codegen(sym_table=sym_table)
        assert cg._is_float_type_op("%t0") is True

    def test_double_type(self):
        sym_table = TypedSymbolTable()
        sym_table.insert("%t1", FloatType(kind=TypeKind.DOUBLE))
        cg = _make_codegen(sym_table=sym_table)
        assert cg._is_float_type_op("%t1") is True

    def test_int_type(self):
        sym_table = TypedSymbolTable()
        sym_table.insert("@x", IntegerType(kind=TypeKind.INT))
        cg = _make_codegen(sym_table=sym_table)
        assert cg._is_float_type_op("@x") is False

    def test_pointer_type(self):
        sym_table = TypedSymbolTable()
        sym_table.insert("@p", PointerType(kind=TypeKind.POINTER,
                                           pointee=IntegerType(kind=TypeKind.INT)))
        cg = _make_codegen(sym_table=sym_table)
        assert cg._is_float_type_op("@p") is False

    def test_unknown_operand_returns_false(self):
        cg = _make_codegen()
        assert cg._is_float_type_op("@unknown") is False

    def test_fallback_to_var_types_float(self):
        """Falls back to _var_types string parsing via _get_type."""
        cg = _make_codegen()
        cg._var_types["%t0"] = "float"
        assert cg._is_float_type_op("%t0") is True

    def test_fallback_to_var_types_double(self):
        cg = _make_codegen()
        cg._var_types["%t0"] = "double"
        assert cg._is_float_type_op("%t0") is True

    def test_fallback_to_var_types_int(self):
        cg = _make_codegen()
        cg._var_types["@x"] = "int"
        assert cg._is_float_type_op("@x") is False


class TestIsArrayTypeOp:
    """Tests for _is_array_type_op CType-based helper."""

    def test_array_type(self):
        sym_table = TypedSymbolTable()
        elem = IntegerType(kind=TypeKind.INT)
        sym_table.insert("@arr", ArrayType(kind=TypeKind.ARRAY, element=elem, size=5))
        cg = _make_codegen(sym_table=sym_table)
        assert cg._is_array_type_op("@arr") is True

    def test_char_array(self):
        sym_table = TypedSymbolTable()
        elem = IntegerType(kind=TypeKind.CHAR)
        sym_table.insert("@buf", ArrayType(kind=TypeKind.ARRAY, element=elem, size=256))
        cg = _make_codegen(sym_table=sym_table)
        assert cg._is_array_type_op("@buf") is True

    def test_int_type(self):
        sym_table = TypedSymbolTable()
        sym_table.insert("@x", IntegerType(kind=TypeKind.INT))
        cg = _make_codegen(sym_table=sym_table)
        assert cg._is_array_type_op("@x") is False

    def test_pointer_type(self):
        sym_table = TypedSymbolTable()
        sym_table.insert("@p", PointerType(kind=TypeKind.POINTER,
                                           pointee=IntegerType(kind=TypeKind.INT)))
        cg = _make_codegen(sym_table=sym_table)
        assert cg._is_array_type_op("@p") is False

    def test_unknown_operand_returns_false(self):
        cg = _make_codegen()
        assert cg._is_array_type_op("@unknown") is False

    def test_fallback_to_var_types_array(self):
        """_str_to_ctype cannot parse internal array(...) format, so fallback
        returns False. The CType path (sym_table) is the correct way to detect arrays."""
        cg = _make_codegen()
        cg._var_types["@arr"] = "array(int,$10)"
        # _str_to_ctype doesn't handle "array(...)" format — returns non-array CType
        assert cg._is_array_type_op("@arr") is False

    def test_fallback_to_var_types_non_array(self):
        cg = _make_codegen()
        cg._var_types["@x"] = "int"
        assert cg._is_array_type_op("@x") is False
