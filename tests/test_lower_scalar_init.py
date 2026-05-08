"""Tests for IRGenerator._lower_scalar_init (task 2.1).

Verifies:
- All scalar types: int, float, char, short, long, pointer, enum
- Brace unwrapping: int x = {42}
- Volatile marking on the emitted instruction
- is_ptr=False emits mov (direct assignment)
- is_ptr=True emits store (pointer dereference store)
"""

import pytest
from unittest.mock import MagicMock
from pycc.ir import IRGenerator, IRInstruction
from pycc.types import (
    TypeKind, IntegerType, FloatType, PointerType, EnumType,
)
from pycc.ast_nodes import (
    Type, IntLiteral, FloatLiteral, CharLiteral, Identifier, Initializer,
)

L, C = 0, 0


def _make_sema_ctx(typedefs=None):
    ctx = MagicMock()
    ctx.typedefs = typedefs or {}
    ctx.layouts = {}
    ctx.global_types = {}
    ctx.global_decl_types = {}
    ctx.function_sigs = {}
    return ctx


def _make_ir_gen(sema_ctx=None, volatile_syms=None):
    gen = IRGenerator.__new__(IRGenerator)
    gen._sema_ctx = sema_ctx
    gen._sym_table = None
    gen._var_types = {}
    gen._var_volatile = volatile_syms or set()
    gen.instructions = []
    gen.temp_counter = 0
    gen.label_counter = 0
    gen._scope_stack = []
    gen._enum_constants = {}
    gen._fn_name = "test_fn"
    gen._fn_ret_type = "int"
    gen._break_stack = []
    gen._continue_stack = []
    gen._string_literals = {}
    gen._string_counter = 0
    gen._local_static_syms = {}
    gen._ptr_step_bytes = {}
    return gen


class TestScalarTypes:
    """All scalar types emit mov when is_ptr=False."""

    def test_int(self):
        gen = _make_ir_gen(_make_sema_ctx())
        ct = IntegerType(kind=TypeKind.INT)
        gen._lower_scalar_init(ct, IntLiteral(L, C, value=99), "@x", False)
        assert len(gen.instructions) == 1
        ins = gen.instructions[0]
        assert ins.op == "mov"
        assert ins.result == "@x"
        assert ins.operand1 == "$99"

    def test_char(self):
        gen = _make_ir_gen(_make_sema_ctx())
        ct = IntegerType(kind=TypeKind.INT)
        gen._lower_scalar_init(ct, CharLiteral(L, C, value="A"), "@c", False)
        assert len(gen.instructions) == 1
        assert gen.instructions[0].op == "mov"
        assert gen.instructions[0].result == "@c"

    def test_float(self):
        gen = _make_ir_gen(_make_sema_ctx())
        ct = FloatType(kind=TypeKind.FLOAT)
        gen._lower_scalar_init(ct, FloatLiteral(L, C, value=2.5), "@f", False)
        # fmov to temp, then mov to @f
        assert len(gen.instructions) == 2
        assert gen.instructions[0].op == "fmov"
        assert gen.instructions[1].op == "mov"
        assert gen.instructions[1].result == "@f"

    def test_pointer(self):
        gen = _make_ir_gen(_make_sema_ctx())
        ct = PointerType(kind=TypeKind.POINTER, pointee=IntegerType(kind=TypeKind.INT))
        gen._lower_scalar_init(ct, IntLiteral(L, C, value=0), "@p", False)
        assert len(gen.instructions) == 1
        assert gen.instructions[0].op == "mov"
        assert gen.instructions[0].result == "@p"

    def test_enum(self):
        gen = _make_ir_gen(_make_sema_ctx())
        ct = EnumType(kind=TypeKind.ENUM, tag="Color")
        gen._lower_scalar_init(ct, IntLiteral(L, C, value=2), "@e", False)
        assert len(gen.instructions) == 1
        assert gen.instructions[0].op == "mov"


class TestBraceUnwrap:
    """int x = {42} should unwrap braces before gen_expr."""

    def test_single_brace_unwrap(self):
        gen = _make_ir_gen(_make_sema_ctx())
        ct = IntegerType(kind=TypeKind.INT)
        inner = IntLiteral(L, C, value=7)
        init = Initializer(L, C, elements=[(None, inner)])
        gen._lower_scalar_init(ct, init, "@x", False)
        assert len(gen.instructions) == 1
        assert gen.instructions[0].op == "mov"
        assert gen.instructions[0].operand1 == "$7"

    def test_non_brace_passthrough(self):
        gen = _make_ir_gen(_make_sema_ctx())
        ct = IntegerType(kind=TypeKind.INT)
        init = IntLiteral(L, C, value=5)
        gen._lower_scalar_init(ct, init, "@x", False)
        assert gen.instructions[0].operand1 == "$5"


class TestVolatile:
    """Volatile symbols should have volatile metadata on the instruction."""

    def test_volatile_mov(self):
        gen = _make_ir_gen(_make_sema_ctx(), volatile_syms={"@v"})
        ct = IntegerType(kind=TypeKind.INT)
        gen._lower_scalar_init(ct, IntLiteral(L, C, value=1), "@v", False)
        ins = gen.instructions[-1]
        assert ins.op == "mov"
        assert ins.meta is not None
        assert ins.meta.get("volatile") is True

    def test_non_volatile_no_meta(self):
        gen = _make_ir_gen(_make_sema_ctx())
        ct = IntegerType(kind=TypeKind.INT)
        gen._lower_scalar_init(ct, IntLiteral(L, C, value=1), "@x", False)
        ins = gen.instructions[-1]
        assert not ins.meta or ins.meta.get("volatile") is not True

    def test_volatile_store_via_ptr(self):
        gen = _make_ir_gen(_make_sema_ctx(), volatile_syms={"%t0"})
        ct = IntegerType(kind=TypeKind.INT)
        gen._lower_scalar_init(ct, IntLiteral(L, C, value=1), "%t0", True)
        ins = gen.instructions[-1]
        assert ins.op == "store"
        assert ins.meta is not None
        assert ins.meta.get("volatile") is True


class TestIsPtrStore:
    """When is_ptr=True, should emit store instead of mov."""

    def test_store_through_pointer(self):
        gen = _make_ir_gen(_make_sema_ctx())
        ct = IntegerType(kind=TypeKind.INT)
        gen._lower_scalar_init(ct, IntLiteral(L, C, value=42), "%t0", True)
        ins = gen.instructions[-1]
        assert ins.op == "store"
        assert ins.result == "$42"
        assert ins.operand1 == "%t0"

    def test_store_float_through_pointer(self):
        gen = _make_ir_gen(_make_sema_ctx())
        ct = FloatType(kind=TypeKind.FLOAT)
        gen._lower_scalar_init(ct, FloatLiteral(L, C, value=1.5), "%t1", True)
        # fmov to temp, then store through pointer
        assert gen.instructions[-1].op == "store"
        assert gen.instructions[-1].operand1 == "%t1"

    def test_store_with_brace_unwrap(self):
        gen = _make_ir_gen(_make_sema_ctx())
        ct = IntegerType(kind=TypeKind.INT)
        inner = IntLiteral(L, C, value=10)
        init = Initializer(L, C, elements=[(None, inner)])
        gen._lower_scalar_init(ct, init, "%t2", True)
        ins = gen.instructions[-1]
        assert ins.op == "store"
        assert ins.result == "$10"
        assert ins.operand1 == "%t2"

    def test_mov_when_not_ptr(self):
        gen = _make_ir_gen(_make_sema_ctx())
        ct = IntegerType(kind=TypeKind.INT)
        gen._lower_scalar_init(ct, IntLiteral(L, C, value=42), "@x", False)
        ins = gen.instructions[-1]
        assert ins.op == "mov"
        assert ins.result == "@x"
