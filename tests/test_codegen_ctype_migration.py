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
