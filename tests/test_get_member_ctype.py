"""Tests for IRGenerator._get_member_ctype helper (task 1.1).

Verifies:
- Scalar members return the correct resolved CType
- Array members (1D) return ArrayType wrapping the element CType
- Multi-dimensional array members return nested ArrayType
- Typedef members are resolved to underlying types
- Missing member / missing layout returns None
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
    """Build a StructLayout from a list of (name, Type, size) tuples.

    array_info: dict of member_name -> (array_size, array_dims)
    """
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


class TestGetMemberCtypeScalar:
    """Scalar members should return the element CType directly."""

    def test_int_member(self):
        ctx = _make_sema_ctx()
        gen = _make_ir_gen(ctx)
        layout = _make_layout("struct", "S", [
            ("x", Type(base="int", line=0, column=0), 4),
            ("y", Type(base="float", line=0, column=0), 4),
        ])
        ct = gen._get_member_ctype(layout, "x", ctx)
        assert ct is not None
        assert ct.kind == TypeKind.INT

    def test_float_member(self):
        ctx = _make_sema_ctx()
        gen = _make_ir_gen(ctx)
        layout = _make_layout("struct", "S", [
            ("x", Type(base="int", line=0, column=0), 4),
            ("y", Type(base="float", line=0, column=0), 4),
        ])
        ct = gen._get_member_ctype(layout, "y", ctx)
        assert ct is not None
        assert ct.kind == TypeKind.FLOAT

    def test_pointer_member(self):
        ctx = _make_sema_ctx()
        gen = _make_ir_gen(ctx)
        layout = _make_layout("struct", "S", [
            ("p", Type(base="int", is_pointer=True, pointer_level=1, line=0, column=0), 8),
        ])
        ct = gen._get_member_ctype(layout, "p", ctx)
        assert ct is not None
        assert ct.kind == TypeKind.POINTER

    def test_char_member(self):
        ctx = _make_sema_ctx()
        gen = _make_ir_gen(ctx)
        layout = _make_layout("struct", "S", [
            ("c", Type(base="char", line=0, column=0), 1),
        ])
        ct = gen._get_member_ctype(layout, "c", ctx)
        assert ct is not None
        assert ct.kind == TypeKind.CHAR


class TestGetMemberCtypeArray:
    """Array members should return ArrayType wrapping the element CType."""

    def test_1d_int_array(self):
        ctx = _make_sema_ctx()
        gen = _make_ir_gen(ctx)
        layout = _make_layout("struct", "S", [
            ("arr", Type(base="int", line=0, column=0), 40),
        ], array_info={"arr": (10, None)})
        ct = gen._get_member_ctype(layout, "arr", ctx)
        assert ct is not None
        assert isinstance(ct, CArrayType)
        assert ct.kind == TypeKind.ARRAY
        assert ct.size == 10
        assert ct.element.kind == TypeKind.INT

    def test_1d_char_array(self):
        ctx = _make_sema_ctx()
        gen = _make_ir_gen(ctx)
        layout = _make_layout("struct", "S", [
            ("name", Type(base="char", line=0, column=0), 32),
        ], array_info={"name": (32, None)})
        ct = gen._get_member_ctype(layout, "name", ctx)
        assert ct is not None
        assert isinstance(ct, CArrayType)
        assert ct.size == 32
        assert ct.element.kind == TypeKind.CHAR

    def test_2d_array(self):
        """int matrix[3][4] should produce ArrayType(ArrayType(int, 4), 3)."""
        ctx = _make_sema_ctx()
        gen = _make_ir_gen(ctx)
        layout = _make_layout("struct", "S", [
            ("matrix", Type(base="int", line=0, column=0), 48),
        ], array_info={"matrix": (12, [3, 4])})
        ct = gen._get_member_ctype(layout, "matrix", ctx)
        assert ct is not None
        assert isinstance(ct, CArrayType)
        assert ct.size == 3
        inner = ct.element
        assert isinstance(inner, CArrayType)
        assert inner.size == 4
        assert inner.element.kind == TypeKind.INT

    def test_3d_array(self):
        """int cube[2][3][4] -> ArrayType(ArrayType(ArrayType(int,4),3),2)."""
        ctx = _make_sema_ctx()
        gen = _make_ir_gen(ctx)
        layout = _make_layout("struct", "S", [
            ("cube", Type(base="int", line=0, column=0), 96),
        ], array_info={"cube": (24, [2, 3, 4])})
        ct = gen._get_member_ctype(layout, "cube", ctx)
        assert ct is not None
        assert isinstance(ct, CArrayType)
        assert ct.size == 2
        mid = ct.element
        assert isinstance(mid, CArrayType)
        assert mid.size == 3
        inner = mid.element
        assert isinstance(inner, CArrayType)
        assert inner.size == 4
        assert inner.element.kind == TypeKind.INT


class TestGetMemberCtypeTypedef:
    """Typedef members should be resolved to underlying types."""

    def test_typedef_int(self):
        td_type = Type(base="int", line=0, column=0)
        ctx = _make_sema_ctx(typedefs={"myint": td_type})
        gen = _make_ir_gen(ctx)
        layout = _make_layout("struct", "S", [
            ("val", Type(base="myint", line=0, column=0), 4),
        ])
        ct = gen._get_member_ctype(layout, "val", ctx)
        assert ct is not None
        assert ct.kind == TypeKind.INT

    def test_typedef_struct(self):
        td_type = Type(base="struct Inner", line=0, column=0)
        ctx = _make_sema_ctx(typedefs={"Inner_t": td_type})
        gen = _make_ir_gen(ctx)
        layout = _make_layout("struct", "S", [
            ("inner", Type(base="Inner_t", line=0, column=0), 16),
        ])
        ct = gen._get_member_ctype(layout, "inner", ctx)
        assert ct is not None
        assert ct.kind == TypeKind.STRUCT


class TestGetMemberCtypeEdgeCases:
    """Edge cases: missing layout, missing member, None sema_ctx."""

    def test_none_layout(self):
        ctx = _make_sema_ctx()
        gen = _make_ir_gen(ctx)
        assert gen._get_member_ctype(None, "x", ctx) is None

    def test_none_sema_ctx(self):
        gen = _make_ir_gen(None)
        layout = _make_layout("struct", "S", [
            ("x", Type(base="int", line=0, column=0), 4),
        ])
        assert gen._get_member_ctype(layout, "x") is None

    def test_missing_member(self):
        ctx = _make_sema_ctx()
        gen = _make_ir_gen(ctx)
        layout = _make_layout("struct", "S", [
            ("x", Type(base="int", line=0, column=0), 4),
        ])
        assert gen._get_member_ctype(layout, "nonexistent", ctx) is None

    def test_empty_member_decl_types(self):
        ctx = _make_sema_ctx()
        gen = _make_ir_gen(ctx)
        layout = StructLayout(
            kind="struct", name="S", size=4, align=4,
            member_offsets={"x": 0}, member_sizes={"x": 4},
            member_types={"x": "int"}, member_decl_types=None,
        )
        assert gen._get_member_ctype(layout, "x", ctx) is None

    def test_fallback_to_self_sema_ctx(self):
        """When sema_ctx param is None, should use self._sema_ctx."""
        ctx = _make_sema_ctx()
        gen = _make_ir_gen(ctx)
        layout = _make_layout("struct", "S", [
            ("x", Type(base="int", line=0, column=0), 4),
        ])
        ct = gen._get_member_ctype(layout, "x")
        assert ct is not None
        assert ct.kind == TypeKind.INT

    def test_union_member(self):
        ctx = _make_sema_ctx()
        gen = _make_ir_gen(ctx)
        layout = _make_layout("union", "U", [
            ("i", Type(base="int", line=0, column=0), 4),
            ("f", Type(base="float", line=0, column=0), 4),
        ])
        ct_i = gen._get_member_ctype(layout, "i", ctx)
        ct_f = gen._get_member_ctype(layout, "f", ctx)
        assert ct_i.kind == TypeKind.INT
        assert ct_f.kind == TypeKind.FLOAT
