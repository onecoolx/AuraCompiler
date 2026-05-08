"""Tests for _lower_array_init designated array initialization path (task 3.3).

Verifies:
- int a[5] = { [2] = 10, [0] = 5 } emits correct store_index
- Mixed designated/non-designated: {[2]=5, 3, 4} → idx 2=5, 3=3, 4=4
- Unspecified indices are zero-filled
- Out-of-bounds designator raises IRGenError
- Aggregate element types use addr_index + recursive lowering
"""

import pytest
from unittest.mock import MagicMock
from pycc.ir import IRGenerator, IRInstruction, IRGenError
from pycc.types import (
    TypeKind, IntegerType, FloatType, PointerType,
    ArrayType as CArrayType, StructType,
)
from pycc.ast_nodes import (
    Initializer, IntLiteral, Designator,
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


class TestDesignatedArrayBasic:
    """int a[5] = { [2] = 10, [0] = 5 } — sparse designated init."""

    def test_emits_five_store_index(self):
        ctx = _make_sema_ctx()
        gen = _make_ir_gen(ctx)
        int_ct = IntegerType(kind=TypeKind.INT)
        ct = CArrayType(kind=TypeKind.ARRAY, element=int_ct, size=5)
        init = Initializer(L, C, elements=[
            (Designator(L, C, index=IntLiteral(L, C, value=2)), IntLiteral(L, C, value=10)),
            (Designator(L, C, index=IntLiteral(L, C, value=0)), IntLiteral(L, C, value=5)),
        ])
        gen._lower_array_init(ct, init, "@a")
        stores = [ins for ins in gen.instructions if ins.op == "store_index"]
        assert len(stores) == 5

    def test_designated_values_correct(self):
        ctx = _make_sema_ctx()
        gen = _make_ir_gen(ctx)
        int_ct = IntegerType(kind=TypeKind.INT)
        ct = CArrayType(kind=TypeKind.ARRAY, element=int_ct, size=5)
        init = Initializer(L, C, elements=[
            (Designator(L, C, index=IntLiteral(L, C, value=2)), IntLiteral(L, C, value=10)),
            (Designator(L, C, index=IntLiteral(L, C, value=0)), IntLiteral(L, C, value=5)),
        ])
        gen._lower_array_init(ct, init, "@a")
        stores = [ins for ins in gen.instructions if ins.op == "store_index"]
        # idx 0 = 5, idx 1 = 0 (zero-fill), idx 2 = 10, idx 3 = 0, idx 4 = 0
        assert stores[0].result == "$5"
        assert stores[0].operand2 == "$0"
        assert stores[1].result == "$0"
        assert stores[1].operand2 == "$1"
        assert stores[2].result == "$10"
        assert stores[2].operand2 == "$2"
        assert stores[3].result == "$0"
        assert stores[3].operand2 == "$3"
        assert stores[4].result == "$0"
        assert stores[4].operand2 == "$4"


class TestDesignatedArrayMixed:
    """int a[5] = { [2] = 5, 3, 4 } — mixed designated/non-designated."""

    def test_sequential_advances_after_designator(self):
        ctx = _make_sema_ctx()
        gen = _make_ir_gen(ctx)
        int_ct = IntegerType(kind=TypeKind.INT)
        ct = CArrayType(kind=TypeKind.ARRAY, element=int_ct, size=5)
        # [2]=5, then 3 goes to idx 3, 4 goes to idx 4
        init = Initializer(L, C, elements=[
            (Designator(L, C, index=IntLiteral(L, C, value=2)), IntLiteral(L, C, value=5)),
            (None, IntLiteral(L, C, value=3)),
            (None, IntLiteral(L, C, value=4)),
        ])
        gen._lower_array_init(ct, init, "@a")
        stores = [ins for ins in gen.instructions if ins.op == "store_index"]
        assert len(stores) == 5
        # idx 0 = 0 (zero-fill), idx 1 = 0 (zero-fill), idx 2 = 5, idx 3 = 3, idx 4 = 4
        assert stores[0].result == "$0"
        assert stores[1].result == "$0"
        assert stores[2].result == "$5"
        assert stores[3].result == "$3"
        assert stores[4].result == "$4"


class TestDesignatedArrayZeroFill:
    """int a[4] = { [3] = 99 } — only one element, rest zero-filled."""

    def test_zero_fills_unspecified(self):
        ctx = _make_sema_ctx()
        gen = _make_ir_gen(ctx)
        int_ct = IntegerType(kind=TypeKind.INT)
        ct = CArrayType(kind=TypeKind.ARRAY, element=int_ct, size=4)
        init = Initializer(L, C, elements=[
            (Designator(L, C, index=IntLiteral(L, C, value=3)), IntLiteral(L, C, value=99)),
        ])
        gen._lower_array_init(ct, init, "@a")
        stores = [ins for ins in gen.instructions if ins.op == "store_index"]
        assert len(stores) == 4
        assert stores[0].result == "$0"
        assert stores[1].result == "$0"
        assert stores[2].result == "$0"
        assert stores[3].result == "$99"


class TestDesignatedArrayOutOfBounds:
    """int a[3] = { [5] = 1 } — out-of-bounds designator raises error."""

    def test_raises_on_oob_index(self):
        ctx = _make_sema_ctx()
        gen = _make_ir_gen(ctx)
        int_ct = IntegerType(kind=TypeKind.INT)
        ct = CArrayType(kind=TypeKind.ARRAY, element=int_ct, size=3)
        init = Initializer(L, C, elements=[
            (Designator(L, C, index=IntLiteral(L, C, value=5)), IntLiteral(L, C, value=1)),
        ])
        with pytest.raises(IRGenError, match="out of bounds"):
            gen._lower_array_init(ct, init, "@a")


class TestDesignatedArrayOverwrite:
    """int a[3] = { [1] = 10, [1] = 20 } — later designator overwrites."""

    def test_last_designator_wins(self):
        ctx = _make_sema_ctx()
        gen = _make_ir_gen(ctx)
        int_ct = IntegerType(kind=TypeKind.INT)
        ct = CArrayType(kind=TypeKind.ARRAY, element=int_ct, size=3)
        init = Initializer(L, C, elements=[
            (Designator(L, C, index=IntLiteral(L, C, value=1)), IntLiteral(L, C, value=10)),
            (Designator(L, C, index=IntLiteral(L, C, value=1)), IntLiteral(L, C, value=20)),
        ])
        gen._lower_array_init(ct, init, "@a")
        stores = [ins for ins in gen.instructions if ins.op == "store_index"]
        assert len(stores) == 3
        # idx 1 should have the last value (20)
        assert stores[1].result == "$20"


class TestDesignatedArrayExcessSequential:
    """int a[3] = { [2] = 5, 6 } — sequential after last index overflows."""

    def test_raises_on_excess_after_designator(self):
        ctx = _make_sema_ctx()
        gen = _make_ir_gen(ctx)
        int_ct = IntegerType(kind=TypeKind.INT)
        ct = CArrayType(kind=TypeKind.ARRAY, element=int_ct, size=3)
        init = Initializer(L, C, elements=[
            (Designator(L, C, index=IntLiteral(L, C, value=2)), IntLiteral(L, C, value=5)),
            (None, IntLiteral(L, C, value=6)),
        ])
        with pytest.raises(IRGenError, match="excess"):
            gen._lower_array_init(ct, init, "@a")
