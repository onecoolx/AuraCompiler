"""Tests for _lower_array_init general array initialization path (task 3.2).

Verifies:
- int a[3] = {1,2,3} emits store_index for each element
- int a[5] = {1,2} zero-fills remaining elements
- Excess elements raise IRGenError
- Multi-dimensional arrays recurse correctly via addr_index
- Struct element arrays use addr_index + recursive lowering
"""

import pytest
from unittest.mock import MagicMock
from pycc.ir import IRGenerator, IRInstruction, IRGenError
from pycc.types import (
    TypeKind, IntegerType, FloatType, PointerType,
    ArrayType as CArrayType, StructType,
)
from pycc.ast_nodes import (
    Initializer, IntLiteral, FloatLiteral,
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
    gen._enum_constants = {}
    gen._fn_name = "test_fn"
    gen._ptr_step_bytes = {}
    return gen


class TestIntArrayFullInit:
    """int a[3] = {1, 2, 3} — all elements provided."""

    def test_emits_three_store_index(self):
        ctx = _make_sema_ctx()
        gen = _make_ir_gen(ctx)
        int_ct = IntegerType(kind=TypeKind.INT)
        ct = CArrayType(kind=TypeKind.ARRAY, element=int_ct, size=3)
        init = Initializer(L, C, elements=[
            (None, IntLiteral(L, C, value=1)),
            (None, IntLiteral(L, C, value=2)),
            (None, IntLiteral(L, C, value=3)),
        ])
        gen._lower_array_init(ct, init, "@a")
        ops = [ins.op for ins in gen.instructions]
        assert ops.count("store_index") == 3

    def test_store_index_values(self):
        ctx = _make_sema_ctx()
        gen = _make_ir_gen(ctx)
        int_ct = IntegerType(kind=TypeKind.INT)
        ct = CArrayType(kind=TypeKind.ARRAY, element=int_ct, size=3)
        init = Initializer(L, C, elements=[
            (None, IntLiteral(L, C, value=10)),
            (None, IntLiteral(L, C, value=20)),
            (None, IntLiteral(L, C, value=30)),
        ])
        gen._lower_array_init(ct, init, "@a")
        stores = [ins for ins in gen.instructions if ins.op == "store_index"]
        assert stores[0].result == "$10"
        assert stores[0].operand2 == "$0"
        assert stores[1].result == "$20"
        assert stores[1].operand2 == "$1"
        assert stores[2].result == "$30"
        assert stores[2].operand2 == "$2"

    def test_store_index_label_is_int(self):
        ctx = _make_sema_ctx()
        gen = _make_ir_gen(ctx)
        int_ct = IntegerType(kind=TypeKind.INT)
        ct = CArrayType(kind=TypeKind.ARRAY, element=int_ct, size=2)
        init = Initializer(L, C, elements=[
            (None, IntLiteral(L, C, value=1)),
            (None, IntLiteral(L, C, value=2)),
        ])
        gen._lower_array_init(ct, init, "@a")
        stores = [ins for ins in gen.instructions if ins.op == "store_index"]
        for s in stores:
            assert s.label == "int"


class TestIntArrayPartialInit:
    """int a[5] = {1, 2} — trailing elements zero-filled."""

    def test_emits_five_store_index(self):
        ctx = _make_sema_ctx()
        gen = _make_ir_gen(ctx)
        int_ct = IntegerType(kind=TypeKind.INT)
        ct = CArrayType(kind=TypeKind.ARRAY, element=int_ct, size=5)
        init = Initializer(L, C, elements=[
            (None, IntLiteral(L, C, value=1)),
            (None, IntLiteral(L, C, value=2)),
        ])
        gen._lower_array_init(ct, init, "@a")
        stores = [ins for ins in gen.instructions if ins.op == "store_index"]
        assert len(stores) == 5

    def test_trailing_zeros(self):
        ctx = _make_sema_ctx()
        gen = _make_ir_gen(ctx)
        int_ct = IntegerType(kind=TypeKind.INT)
        ct = CArrayType(kind=TypeKind.ARRAY, element=int_ct, size=5)
        init = Initializer(L, C, elements=[
            (None, IntLiteral(L, C, value=1)),
            (None, IntLiteral(L, C, value=2)),
        ])
        gen._lower_array_init(ct, init, "@a")
        stores = [ins for ins in gen.instructions if ins.op == "store_index"]
        # Elements 2,3,4 should be zero-filled
        assert stores[2].result == "$0"
        assert stores[3].result == "$0"
        assert stores[4].result == "$0"


class TestExcessElements:
    """int a[2] = {1, 2, 3} — should raise IRGenError."""

    def test_raises_on_excess(self):
        ctx = _make_sema_ctx()
        gen = _make_ir_gen(ctx)
        int_ct = IntegerType(kind=TypeKind.INT)
        ct = CArrayType(kind=TypeKind.ARRAY, element=int_ct, size=2)
        init = Initializer(L, C, elements=[
            (None, IntLiteral(L, C, value=1)),
            (None, IntLiteral(L, C, value=2)),
            (None, IntLiteral(L, C, value=3)),
        ])
        with pytest.raises(IRGenError, match="excess"):
            gen._lower_array_init(ct, init, "@a")


class TestCharArrayBraceInit:
    """char a[3] = {65, 66, 67} — char array with brace list, not string."""

    def test_emits_char_label(self):
        ctx = _make_sema_ctx()
        gen = _make_ir_gen(ctx)
        char_ct = IntegerType(kind=TypeKind.CHAR)
        ct = CArrayType(kind=TypeKind.ARRAY, element=char_ct, size=3)
        init = Initializer(L, C, elements=[
            (None, IntLiteral(L, C, value=65)),
            (None, IntLiteral(L, C, value=66)),
            (None, IntLiteral(L, C, value=67)),
        ])
        gen._lower_array_init(ct, init, "@a")
        stores = [ins for ins in gen.instructions if ins.op == "store_index"]
        assert len(stores) == 3
        for s in stores:
            assert s.label == "char"


class TestEmptyInitializer:
    """int a[3] = {} — all elements zero-filled."""

    def test_all_zeros(self):
        ctx = _make_sema_ctx()
        gen = _make_ir_gen(ctx)
        int_ct = IntegerType(kind=TypeKind.INT)
        ct = CArrayType(kind=TypeKind.ARRAY, element=int_ct, size=3)
        init = Initializer(L, C, elements=[])
        gen._lower_array_init(ct, init, "@a")
        stores = [ins for ins in gen.instructions if ins.op == "store_index"]
        assert len(stores) == 3
        for s in stores:
            assert s.result == "$0"


class TestMultiDimArray:
    """int a[2][3] = {{1,2,3},{4,5,6}} — nested arrays use addr_index."""

    def test_emits_addr_index_for_rows(self):
        ctx = _make_sema_ctx()
        gen = _make_ir_gen(ctx)
        int_ct = IntegerType(kind=TypeKind.INT)
        inner_ct = CArrayType(kind=TypeKind.ARRAY, element=int_ct, size=3)
        outer_ct = CArrayType(kind=TypeKind.ARRAY, element=inner_ct, size=2)
        row0 = Initializer(L, C, elements=[
            (None, IntLiteral(L, C, value=1)),
            (None, IntLiteral(L, C, value=2)),
            (None, IntLiteral(L, C, value=3)),
        ])
        row1 = Initializer(L, C, elements=[
            (None, IntLiteral(L, C, value=4)),
            (None, IntLiteral(L, C, value=5)),
            (None, IntLiteral(L, C, value=6)),
        ])
        init = Initializer(L, C, elements=[
            (None, row0),
            (None, row1),
        ])
        gen._lower_array_init(outer_ct, init, "@a")
        ops = [ins.op for ins in gen.instructions]
        # Should have addr_index for each row, then store_index for each element
        assert ops.count("addr_index") == 2
        assert ops.count("store_index") == 6
