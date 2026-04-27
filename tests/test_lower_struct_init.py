"""Tests for IRGenerator._lower_struct_init — sequential and union initialization.

Verifies:
- Sequential member initialization emits store_member for each member
- Trailing zero-fill for unspecified members
- Nested struct members use addr_of_member + recursive lowering
- Brace elision: bare expressions consumed for nested aggregate members
- is_ptr=True uses store_member_ptr / addr_of_member_ptr
- Excess elements raise IRGenError
- Empty initializer zero-fills all members
- Union init initializes only the first member per C89 rules
- Union empty init zero-fills the first member
- Designated init delegates to stub (NotImplementedError for task 4.3)
"""

import pytest
from unittest.mock import MagicMock
from pycc.ir import IRGenerator, IRInstruction, IRGenError
from pycc.types import (
    TypeKind, IntegerType, PointerType,
    ArrayType as CArrayType, StructType as CStructType,
)
from pycc.semantics import StructLayout
from pycc.ast_nodes import (
    Type, IntLiteral, Initializer, Designator,
)

L, C = 0, 0


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
    gen._var_volatile = set()
    gen.instructions = []
    gen.temp_counter = 0
    gen.label_counter = 0
    gen._scope_stack = []
    gen._local_arrays = set()
    gen._enum_constants = {}
    gen._fn_name = "test_fn"
    gen._fn_ret_type = "int"
    gen._break_stack = []
    gen._continue_stack = []
    gen._string_literals = {}
    gen._string_counter = 0
    gen._local_static_syms = {}
    gen._ptr_step_bytes = {}
    gen._local_array_dims = {}
    gen._shadow_counter = 0
    return gen


def _make_layout(name, members, kind="struct"):
    """Build a StructLayout with the given members.

    members: list of (name, type_str, offset, size) tuples.
    """
    layout = MagicMock(spec=StructLayout)
    layout.kind = kind
    layout.name = name
    total = 0
    layout.member_offsets = {}
    layout.member_sizes = {}
    layout.member_types = {}
    layout.member_decl_types = {}
    layout.member_array_info = None
    for mname, mtype, moffset, msize in members:
        layout.member_offsets[mname] = moffset
        layout.member_sizes[mname] = msize
        layout.member_types[mname] = mtype
        layout.member_decl_types[mname] = Type(base=mtype, line=0, column=0)
        total = max(total, moffset + msize)
    layout.size = total
    layout.align = 8
    return layout


class TestSequentialInit:
    """Sequential (non-designated) struct initialization."""

    def test_two_int_members(self):
        """struct S { int x; int y; }; struct S s = {1, 2};"""
        layout = _make_layout("S", [
            ("x", "int", 0, 4),
            ("y", "int", 4, 4),
        ])
        ctx = _make_sema_ctx(layouts={"struct S": layout})
        gen = _make_ir_gen(ctx)
        ct = CStructType(kind=TypeKind.STRUCT, tag="S")
        init = Initializer(L, C, elements=[
            (None, IntLiteral(L, C, value=1)),
            (None, IntLiteral(L, C, value=2)),
        ])
        gen._lower_struct_init(ct, init, "@s", False)
        stores = [i for i in gen.instructions if i.op == "store_member"]
        assert len(stores) == 2
        assert stores[0].operand2 == "x"
        assert stores[1].operand2 == "y"

    def test_trailing_zero_fill(self):
        """struct S { int x; int y; int z; }; struct S s = {1};
        y and z should be zero-filled."""
        layout = _make_layout("S", [
            ("x", "int", 0, 4),
            ("y", "int", 4, 4),
            ("z", "int", 8, 4),
        ])
        ctx = _make_sema_ctx(layouts={"struct S": layout})
        gen = _make_ir_gen(ctx)
        ct = CStructType(kind=TypeKind.STRUCT, tag="S")
        init = Initializer(L, C, elements=[
            (None, IntLiteral(L, C, value=42)),
        ])
        gen._lower_struct_init(ct, init, "@s", False)
        stores = [i for i in gen.instructions if i.op == "store_member"]
        assert len(stores) == 3
        assert stores[0].operand2 == "x"
        assert stores[1].operand2 == "y"
        assert stores[2].operand2 == "z"

    def test_empty_initializer_zero_fills_all(self):
        """struct S s = {}; — all members zero-filled."""
        layout = _make_layout("S", [
            ("a", "int", 0, 4),
            ("b", "int", 4, 4),
        ])
        ctx = _make_sema_ctx(layouts={"struct S": layout})
        gen = _make_ir_gen(ctx)
        ct = CStructType(kind=TypeKind.STRUCT, tag="S")
        init = Initializer(L, C, elements=[])
        gen._lower_struct_init(ct, init, "@s", False)
        stores = [i for i in gen.instructions if i.op == "store_member"]
        assert len(stores) == 2

    def test_is_ptr_uses_store_member_ptr(self):
        """When is_ptr=True, should use store_member_ptr."""
        layout = _make_layout("S", [
            ("x", "int", 0, 4),
        ])
        ctx = _make_sema_ctx(layouts={"struct S": layout})
        gen = _make_ir_gen(ctx)
        ct = CStructType(kind=TypeKind.STRUCT, tag="S")
        init = Initializer(L, C, elements=[
            (None, IntLiteral(L, C, value=7)),
        ])
        gen._lower_struct_init(ct, init, "%t0", True)
        stores = [i for i in gen.instructions if i.op == "store_member_ptr"]
        assert len(stores) == 1
        assert stores[0].operand2 == "x"

    def test_excess_elements_raises(self):
        """More elements than members should raise IRGenError."""
        layout = _make_layout("S", [
            ("x", "int", 0, 4),
        ])
        ctx = _make_sema_ctx(layouts={"struct S": layout})
        gen = _make_ir_gen(ctx)
        ct = CStructType(kind=TypeKind.STRUCT, tag="S")
        init = Initializer(L, C, elements=[
            (None, IntLiteral(L, C, value=1)),
            (None, IntLiteral(L, C, value=2)),
        ])
        with pytest.raises(IRGenError, match="excess"):
            gen._lower_struct_init(ct, init, "@s", False)


class TestNestedStruct:
    """Nested struct member initialization."""

    def test_nested_struct_with_braces(self):
        """struct Inner { int a; int b; };
        struct Outer { int x; struct Inner inner; };
        struct Outer o = {1, {2, 3}};"""
        inner_layout = _make_layout("Inner", [
            ("a", "int", 0, 4),
            ("b", "int", 4, 4),
        ])
        outer_layout = _make_layout("Outer", [
            ("x", "int", 0, 4),
            ("inner", "struct Inner", 4, 8),
        ])
        ctx = _make_sema_ctx(layouts={
            "struct Inner": inner_layout,
            "struct Outer": outer_layout,
        })
        gen = _make_ir_gen(ctx)
        ct = CStructType(kind=TypeKind.STRUCT, tag="Outer")
        init = Initializer(L, C, elements=[
            (None, IntLiteral(L, C, value=1)),
            (None, Initializer(L, C, elements=[
                (None, IntLiteral(L, C, value=2)),
                (None, IntLiteral(L, C, value=3)),
            ])),
        ])
        gen._lower_struct_init(ct, init, "@o", False)
        ops = [i.op for i in gen.instructions]
        # x: store_member, inner: addr_of_member + (a: store_member_ptr, b: store_member_ptr)
        assert "store_member" in ops
        assert "addr_of_member" in ops

    def test_brace_elision_for_nested_struct(self):
        """struct Inner { int a; int b; };
        struct Outer { struct Inner inner; int z; };
        struct Outer o = {1, 2, 3};  // brace elision: 1,2 go to inner"""
        inner_layout = _make_layout("Inner", [
            ("a", "int", 0, 4),
            ("b", "int", 4, 4),
        ])
        outer_layout = _make_layout("Outer", [
            ("inner", "struct Inner", 0, 8),
            ("z", "int", 8, 4),
        ])
        ctx = _make_sema_ctx(layouts={
            "struct Inner": inner_layout,
            "struct Outer": outer_layout,
        })
        gen = _make_ir_gen(ctx)
        ct = CStructType(kind=TypeKind.STRUCT, tag="Outer")
        init = Initializer(L, C, elements=[
            (None, IntLiteral(L, C, value=1)),
            (None, IntLiteral(L, C, value=2)),
            (None, IntLiteral(L, C, value=3)),
        ])
        gen._lower_struct_init(ct, init, "@o", False)
        ops = [i.op for i in gen.instructions]
        # inner: addr_of_member + recursive (a: store_member_ptr, b: store_member_ptr)
        # z: store_member
        assert "addr_of_member" in ops
        assert ops.count("store_member_ptr") == 2
        assert ops.count("store_member") == 1


class TestUnionInit:
    """Union initialization — first member only (C89 rule)."""

    def test_union_scalar_first_member(self):
        """union U { int x; float y; }; union U u = {1};
        Only x should be initialized."""
        layout = _make_layout("U", [
            ("x", "int", 0, 4),
            ("y", "float", 0, 4),
        ], kind="union")
        ctx = _make_sema_ctx(layouts={"union U": layout})
        gen = _make_ir_gen(ctx)
        ct = CStructType(kind=TypeKind.UNION, tag="U")
        init = Initializer(L, C, elements=[
            (None, IntLiteral(L, C, value=1)),
        ])
        gen._lower_struct_init(ct, init, "@u", False)
        stores = [i for i in gen.instructions if i.op == "store_member"]
        assert len(stores) == 1
        assert stores[0].operand2 == "x"

    def test_union_empty_initializer_zero_fills(self):
        """union U u = {}; — first member should be zero-filled."""
        layout = _make_layout("U", [
            ("x", "int", 0, 4),
            ("y", "int", 0, 4),
        ], kind="union")
        ctx = _make_sema_ctx(layouts={"union U": layout})
        gen = _make_ir_gen(ctx)
        ct = CStructType(kind=TypeKind.UNION, tag="U")
        init = Initializer(L, C, elements=[])
        gen._lower_struct_init(ct, init, "@u", False)
        stores = [i for i in gen.instructions if i.op == "store_member"]
        assert len(stores) == 1
        assert stores[0].operand2 == "x"

    def test_union_is_ptr_uses_store_member_ptr(self):
        """When is_ptr=True, should use store_member_ptr."""
        layout = _make_layout("U", [
            ("x", "int", 0, 4),
        ], kind="union")
        ctx = _make_sema_ctx(layouts={"union U": layout})
        gen = _make_ir_gen(ctx)
        ct = CStructType(kind=TypeKind.UNION, tag="U")
        init = Initializer(L, C, elements=[
            (None, IntLiteral(L, C, value=7)),
        ])
        gen._lower_struct_init(ct, init, "%t0", True)
        stores = [i for i in gen.instructions if i.op == "store_member_ptr"]
        assert len(stores) == 1
        assert stores[0].operand2 == "x"

    def test_union_nested_struct_first_member(self):
        """union U { struct S inner; int y; }; union U u = {{1, 2}};
        First member is a struct — should use addr_of_member + recursive."""
        inner_layout = _make_layout("S", [
            ("a", "int", 0, 4),
            ("b", "int", 4, 4),
        ])
        union_layout = _make_layout("U", [
            ("inner", "struct S", 0, 8),
            ("y", "int", 0, 4),
        ], kind="union")
        ctx = _make_sema_ctx(layouts={
            "struct S": inner_layout,
            "union U": union_layout,
        })
        gen = _make_ir_gen(ctx)
        ct = CStructType(kind=TypeKind.UNION, tag="U")
        init = Initializer(L, C, elements=[
            (None, Initializer(L, C, elements=[
                (None, IntLiteral(L, C, value=1)),
                (None, IntLiteral(L, C, value=2)),
            ])),
        ])
        gen._lower_struct_init(ct, init, "@u", False)
        ops = [i.op for i in gen.instructions]
        assert "addr_of_member" in ops


class TestDelegation:
    """Designated path delegates to stub."""

    def test_designated_delegates_to_stub(self):
        layout = _make_layout("S", [
            ("x", "int", 0, 4),
            ("y", "int", 4, 4),
        ])
        ctx = _make_sema_ctx(layouts={"struct S": layout})
        gen = _make_ir_gen(ctx)
        ct = CStructType(kind=TypeKind.STRUCT, tag="S")
        desig = Designator(line=0, column=0, member="y", index=None, next=None)
        init = Initializer(L, C, elements=[
            (desig, IntLiteral(L, C, value=99)),
        ])
        with pytest.raises(NotImplementedError, match="task 4.3"):
            gen._lower_struct_init(ct, init, "@s", False)
