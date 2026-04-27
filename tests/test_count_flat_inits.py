"""Tests for IRGenerator._count_flat_inits helper (task 1.3).

Verifies:
- Scalar types return 1
- 1D arrays return element_count * element_flat_count
- Multi-dimensional arrays return product of all dimensions
- Structs return sum of flat counts of all members
- Unions return flat count of first member only (C89)
- Nested struct-in-array and array-in-struct combinations
- Typedef resolution before counting
- Edge cases: None sema_ctx, missing layout
"""

import pytest
from unittest.mock import MagicMock
from pycc.ir import IRGenerator
from pycc.types import (
    TypeKind, IntegerType, FloatType, PointerType,
    ArrayType as CArrayType, StructType as CStructType,
)
from pycc.semantics import StructLayout
from pycc.ast_nodes import Type


def _make_sema_ctx(typedefs=None, layouts=None):
    ctx = MagicMock()
    ctx.typedefs = typedefs or {}
    ctx.layouts = layouts or {}
    ctx.global_types = {}
    ctx.global_decl_types = {}
    ctx.function_sigs = {}
    return ctx


def _make_ir_gen(sema_ctx=None):
    gen = IRGenerator.__new__(IRGenerator)
    gen._sema_ctx = sema_ctx
    gen._sym_table = None
    gen._var_types = {}
    return gen


def _make_layout(kind, name, members, array_info=None):
    offsets, sizes, types_str, decl_types = {}, {}, {}, {}
    offset = 0
    for mname, mtype, msize in members:
        offsets[mname] = offset
        sizes[mname] = msize
        types_str[mname] = mtype.base
        decl_types[mname] = mtype
        offset += msize
    return StructLayout(
        kind=kind, name=name, size=offset, align=8,
        member_offsets=offsets, member_sizes=sizes,
        member_types=types_str, member_decl_types=decl_types,
        member_array_info=array_info,
    )


class TestCountFlatInitsScalar:
    """Scalar types should always return 1."""

    def test_int(self):
        gen = _make_ir_gen(_make_sema_ctx())
        ct = IntegerType(kind=TypeKind.INT)
        assert gen._count_flat_inits(ct) == 1

    def test_char(self):
        gen = _make_ir_gen(_make_sema_ctx())
        ct = IntegerType(kind=TypeKind.CHAR)
        assert gen._count_flat_inits(ct) == 1

    def test_float(self):
        gen = _make_ir_gen(_make_sema_ctx())
        ct = FloatType(kind=TypeKind.FLOAT)
        assert gen._count_flat_inits(ct) == 1

    def test_double(self):
        gen = _make_ir_gen(_make_sema_ctx())
        ct = FloatType(kind=TypeKind.DOUBLE)
        assert gen._count_flat_inits(ct) == 1

    def test_pointer(self):
        gen = _make_ir_gen(_make_sema_ctx())
        ct = PointerType(kind=TypeKind.POINTER, pointee=IntegerType(kind=TypeKind.INT))
        assert gen._count_flat_inits(ct) == 1


class TestCountFlatInitsArray:
    """Arrays should return element_flat_count * size."""

    def test_1d_int_array(self):
        gen = _make_ir_gen(_make_sema_ctx())
        ct = CArrayType(kind=TypeKind.ARRAY, element=IntegerType(kind=TypeKind.INT), size=5)
        assert gen._count_flat_inits(ct) == 5

    def test_1d_char_array(self):
        gen = _make_ir_gen(_make_sema_ctx())
        ct = CArrayType(kind=TypeKind.ARRAY, element=IntegerType(kind=TypeKind.CHAR), size=10)
        assert gen._count_flat_inits(ct) == 10

    def test_2d_array(self):
        """int a[2][3] -> 6 flat elements."""
        gen = _make_ir_gen(_make_sema_ctx())
        inner = CArrayType(kind=TypeKind.ARRAY, element=IntegerType(kind=TypeKind.INT), size=3)
        outer = CArrayType(kind=TypeKind.ARRAY, element=inner, size=2)
        assert gen._count_flat_inits(outer) == 6

    def test_3d_array(self):
        """int a[2][3][4] -> 24 flat elements."""
        gen = _make_ir_gen(_make_sema_ctx())
        d3 = CArrayType(kind=TypeKind.ARRAY, element=IntegerType(kind=TypeKind.INT), size=4)
        d2 = CArrayType(kind=TypeKind.ARRAY, element=d3, size=3)
        d1 = CArrayType(kind=TypeKind.ARRAY, element=d2, size=2)
        assert gen._count_flat_inits(d1) == 24

    def test_zero_size_array(self):
        gen = _make_ir_gen(_make_sema_ctx())
        ct = CArrayType(kind=TypeKind.ARRAY, element=IntegerType(kind=TypeKind.INT), size=0)
        assert gen._count_flat_inits(ct) == 0

    def test_none_size_array(self):
        """Incomplete array (size=None) -> 0."""
        gen = _make_ir_gen(_make_sema_ctx())
        ct = CArrayType(kind=TypeKind.ARRAY, element=IntegerType(kind=TypeKind.INT), size=None)
        assert gen._count_flat_inits(ct) == 0


class TestCountFlatInitsStruct:
    """Structs should return sum of flat counts of all members."""

    def test_simple_struct(self):
        """struct { int x; int y; } -> 2."""
        layout = _make_layout("struct", "S", [
            ("x", Type(base="int", line=0, column=0), 4),
            ("y", Type(base="int", line=0, column=0), 4),
        ])
        ctx = _make_sema_ctx(layouts={"struct S": layout})
        gen = _make_ir_gen(ctx)
        ct = CStructType(kind=TypeKind.STRUCT, tag="S")
        assert gen._count_flat_inits(ct) == 2

    def test_mixed_type_struct(self):
        """struct { int x; float y; char z; } -> 3."""
        layout = _make_layout("struct", "S", [
            ("x", Type(base="int", line=0, column=0), 4),
            ("y", Type(base="float", line=0, column=0), 4),
            ("z", Type(base="char", line=0, column=0), 1),
        ])
        ctx = _make_sema_ctx(layouts={"struct S": layout})
        gen = _make_ir_gen(ctx)
        ct = CStructType(kind=TypeKind.STRUCT, tag="S")
        assert gen._count_flat_inits(ct) == 3

    def test_struct_with_array_member(self):
        """struct { int arr[3]; int y; } -> 4."""
        layout = _make_layout("struct", "S", [
            ("arr", Type(base="int", line=0, column=0), 12),
            ("y", Type(base="int", line=0, column=0), 4),
        ], array_info={"arr": (3, None)})
        ctx = _make_sema_ctx(layouts={"struct S": layout})
        gen = _make_ir_gen(ctx)
        ct = CStructType(kind=TypeKind.STRUCT, tag="S")
        assert gen._count_flat_inits(ct) == 4

    def test_nested_struct(self):
        """struct Outer { struct Inner { int a; int b; } inner; int c; } -> 3."""
        inner_layout = _make_layout("struct", "Inner", [
            ("a", Type(base="int", line=0, column=0), 4),
            ("b", Type(base="int", line=0, column=0), 4),
        ])
        outer_layout = _make_layout("struct", "Outer", [
            ("inner", Type(base="struct Inner", line=0, column=0), 8),
            ("c", Type(base="int", line=0, column=0), 4),
        ])
        ctx = _make_sema_ctx(layouts={
            "struct Inner": inner_layout,
            "struct Outer": outer_layout,
        })
        gen = _make_ir_gen(ctx)
        ct = CStructType(kind=TypeKind.STRUCT, tag="Outer")
        assert gen._count_flat_inits(ct) == 3

    def test_missing_layout_returns_1(self):
        """Unknown struct with no layout -> 1."""
        ctx = _make_sema_ctx()
        gen = _make_ir_gen(ctx)
        ct = CStructType(kind=TypeKind.STRUCT, tag="Unknown")
        assert gen._count_flat_inits(ct) == 1


class TestCountFlatInitsUnion:
    """Unions should return flat count of first member only."""

    def test_simple_union(self):
        """union { int i; float f; } -> 1 (first member is scalar)."""
        layout = _make_layout("union", "U", [
            ("i", Type(base="int", line=0, column=0), 4),
            ("f", Type(base="float", line=0, column=0), 4),
        ])
        ctx = _make_sema_ctx(layouts={"union U": layout})
        gen = _make_ir_gen(ctx)
        ct = CStructType(kind=TypeKind.UNION, tag="U")
        assert gen._count_flat_inits(ct) == 1

    def test_union_first_member_is_array(self):
        """union { int arr[3]; float f; } -> 3 (first member is int[3])."""
        layout = _make_layout("union", "U", [
            ("arr", Type(base="int", line=0, column=0), 12),
            ("f", Type(base="float", line=0, column=0), 4),
        ], array_info={"arr": (3, None)})
        ctx = _make_sema_ctx(layouts={"union U": layout})
        gen = _make_ir_gen(ctx)
        ct = CStructType(kind=TypeKind.UNION, tag="U")
        assert gen._count_flat_inits(ct) == 3


class TestCountFlatInitsTypedef:
    """Typedef types should be resolved before counting."""

    def test_typedef_to_struct(self):
        """typedef struct S MyS; -> resolves to struct S, counts members."""
        layout = _make_layout("struct", "S", [
            ("x", Type(base="int", line=0, column=0), 4),
            ("y", Type(base="int", line=0, column=0), 4),
        ])
        td_type = Type(base="struct S", line=0, column=0)
        ctx = _make_sema_ctx(
            typedefs={"MyS": td_type},
            layouts={"struct S": layout},
        )
        gen = _make_ir_gen(ctx)
        ct = CStructType(kind=TypeKind.STRUCT, tag="MyS")
        assert gen._count_flat_inits(ct) == 2

    def test_typedef_to_int(self):
        """typedef int myint; -> resolves to int, returns 1."""
        td_type = Type(base="int", line=0, column=0)
        ctx = _make_sema_ctx(typedefs={"myint": td_type})
        gen = _make_ir_gen(ctx)
        ct = CStructType(kind=TypeKind.STRUCT, tag="myint")
        assert gen._count_flat_inits(ct) == 1


class TestCountFlatInitsComplex:
    """Complex nested combinations."""

    def test_array_of_structs(self):
        """struct S { int a; int b; }; S arr[3] -> 6."""
        layout = _make_layout("struct", "S", [
            ("a", Type(base="int", line=0, column=0), 4),
            ("b", Type(base="int", line=0, column=0), 4),
        ])
        ctx = _make_sema_ctx(layouts={"struct S": layout})
        gen = _make_ir_gen(ctx)
        elem = CStructType(kind=TypeKind.STRUCT, tag="S")
        ct = CArrayType(kind=TypeKind.ARRAY, element=elem, size=3)
        assert gen._count_flat_inits(ct) == 6

    def test_struct_with_nested_struct_and_array(self):
        """struct O { struct I { int a[2]; } inner; int c; } -> 3."""
        inner_layout = _make_layout("struct", "I", [
            ("a", Type(base="int", line=0, column=0), 8),
        ], array_info={"a": (2, None)})
        outer_layout = _make_layout("struct", "O", [
            ("inner", Type(base="struct I", line=0, column=0), 8),
            ("c", Type(base="int", line=0, column=0), 4),
        ])
        ctx = _make_sema_ctx(layouts={
            "struct I": inner_layout,
            "struct O": outer_layout,
        })
        gen = _make_ir_gen(ctx)
        ct = CStructType(kind=TypeKind.STRUCT, tag="O")
        assert gen._count_flat_inits(ct) == 3

    def test_none_sema_ctx_returns_1_for_struct(self):
        gen = _make_ir_gen(None)
        ct = CStructType(kind=TypeKind.STRUCT, tag="S")
        assert gen._count_flat_inits(ct) == 1
