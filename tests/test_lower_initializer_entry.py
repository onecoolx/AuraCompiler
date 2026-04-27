"""Tests for IRGenerator._lower_initializer unified entry point (task 1.4).

Verifies:
- Typedef resolution before dispatch
- Scalar dispatch: emits mov instruction
- Scalar with braces: unwraps {42} and emits mov
- Struct copy: struct S b = a emits struct_copy
- Union copy: union U b = a emits struct_copy
- Array dispatch: raises NotImplementedError (stub)
- Struct dispatch: raises NotImplementedError (stub)
- Union dispatch: initializes first member only per C89 rules
"""

import pytest
from unittest.mock import MagicMock
from pycc.ir import IRGenerator, IRInstruction
from pycc.types import (
    TypeKind, IntegerType, FloatType, PointerType,
    ArrayType as CArrayType, StructType as CStructType,
    EnumType,
)
from pycc.semantics import StructLayout
from pycc.ast_nodes import (
    Type, IntLiteral, FloatLiteral, Identifier, Initializer,
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
    return gen


def _make_struct_layout(name, size, kind="struct"):
    layout = MagicMock(spec=StructLayout)
    layout.kind = kind
    layout.name = name
    layout.size = size
    layout.align = 8
    layout.member_offsets = {"x": 0, "y": 4}
    layout.member_sizes = {"x": 4, "y": 4}
    layout.member_types = {"x": "int", "y": "int"}
    layout.member_decl_types = {
        "x": Type(base="int", line=0, column=0),
        "y": Type(base="int", line=0, column=0),
    }
    layout.member_array_info = None
    return layout


class TestScalarDispatch:
    """Scalar types should dispatch to _lower_scalar_init."""

    def test_int_scalar(self):
        ctx = _make_sema_ctx()
        gen = _make_ir_gen(ctx)
        ct = IntegerType(kind=TypeKind.INT)
        init = IntLiteral(L, C, value=42)
        gen._lower_initializer(ct, init, "@x", False)
        assert len(gen.instructions) == 1
        assert gen.instructions[0].op == "mov"
        assert gen.instructions[0].result == "@x"

    def test_float_scalar(self):
        ctx = _make_sema_ctx()
        gen = _make_ir_gen(ctx)
        ct = FloatType(kind=TypeKind.FLOAT)
        init = FloatLiteral(L, C, value=3.14)
        gen._lower_initializer(ct, init, "@f", False)
        # _gen_expr emits fmov to temp, then _lower_scalar_init emits mov to @f
        assert len(gen.instructions) == 2
        assert gen.instructions[0].op == "fmov"
        assert gen.instructions[1].op == "mov"
        assert gen.instructions[1].result == "@f"

    def test_pointer_scalar(self):
        ctx = _make_sema_ctx()
        gen = _make_ir_gen(ctx)
        ct = PointerType(kind=TypeKind.POINTER, pointee=IntegerType(kind=TypeKind.INT))
        init = IntLiteral(L, C, value=0)
        gen._lower_initializer(ct, init, "@p", False)
        assert len(gen.instructions) == 1
        assert gen.instructions[0].op == "mov"
        assert gen.instructions[0].result == "@p"

    def test_enum_scalar(self):
        ctx = _make_sema_ctx()
        gen = _make_ir_gen(ctx)
        ct = EnumType(kind=TypeKind.ENUM, tag="Color")
        init = IntLiteral(L, C, value=1)
        gen._lower_initializer(ct, init, "@e", False)
        assert len(gen.instructions) == 1
        assert gen.instructions[0].op == "mov"

    def test_scalar_with_braces_unwrap(self):
        """int x = {42} should unwrap braces and emit mov."""
        ctx = _make_sema_ctx()
        gen = _make_ir_gen(ctx)
        ct = IntegerType(kind=TypeKind.INT)
        inner = IntLiteral(L, C, value=42)
        init = Initializer(L, C, elements=[(None, inner)])
        gen._lower_initializer(ct, init, "@x", False)
        assert len(gen.instructions) == 1
        assert gen.instructions[0].op == "mov"
        assert gen.instructions[0].result == "@x"


class TestTypedefResolution:
    """Typedef names should be resolved before dispatch."""

    def test_typedef_to_int(self):
        """typedef int myint; myint x = 42; should dispatch to scalar."""
        td_type = Type(base="int", line=0, column=0)
        ctx = _make_sema_ctx(typedefs={"myint": td_type})
        gen = _make_ir_gen(ctx)
        ct = CStructType(kind=TypeKind.STRUCT, tag="myint")
        init = IntLiteral(L, C, value=42)
        gen._lower_initializer(ct, init, "@x", False)
        assert len(gen.instructions) == 1
        assert gen.instructions[0].op == "mov"

    def test_typedef_to_float(self):
        """typedef float myfloat; myfloat f = 1.0; should dispatch to scalar."""
        td_type = Type(base="float", line=0, column=0)
        ctx = _make_sema_ctx(typedefs={"myfloat": td_type})
        gen = _make_ir_gen(ctx)
        ct = CStructType(kind=TypeKind.STRUCT, tag="myfloat")
        init = FloatLiteral(L, C, value=1.0)
        gen._lower_initializer(ct, init, "@f", False)
        assert len(gen.instructions) == 2
        assert gen.instructions[0].op == "fmov"
        assert gen.instructions[1].op == "mov"
        assert gen.instructions[1].result == "@f"


class TestStructCopy:
    """struct S b = a should emit struct_copy."""

    def test_struct_copy_with_layout(self):
        layout = _make_struct_layout("S", 8)
        ctx = _make_sema_ctx(layouts={"struct S": layout})
        gen = _make_ir_gen(ctx)
        gen._var_types["@a"] = "struct S"
        ct = CStructType(kind=TypeKind.STRUCT, tag="S")
        init = Identifier(L, C, name="a")
        gen._lower_initializer(ct, init, "@b", False)
        # Should have: load @a, then struct_copy
        struct_copies = [i for i in gen.instructions if i.op == "struct_copy"]
        assert len(struct_copies) == 1
        assert struct_copies[0].result == "@b"
        assert struct_copies[0].meta["size"] == 8

    def test_union_copy_with_layout(self):
        layout = _make_struct_layout("U", 4, kind="union")
        ctx = _make_sema_ctx(layouts={"union U": layout})
        gen = _make_ir_gen(ctx)
        gen._var_types["@a"] = "union U"
        ct = CStructType(kind=TypeKind.UNION, tag="U")
        init = Identifier(L, C, name="a")
        gen._lower_initializer(ct, init, "@b", False)
        struct_copies = [i for i in gen.instructions if i.op == "struct_copy"]
        assert len(struct_copies) == 1
        assert struct_copies[0].result == "@b"
        assert struct_copies[0].meta["size"] == 4

    def test_struct_copy_no_layout_falls_back_to_mov(self):
        """If layout not found (size=0), fall back to mov."""
        ctx = _make_sema_ctx(layouts={})
        gen = _make_ir_gen(ctx)
        gen._var_types["@a"] = "struct S"
        ct = CStructType(kind=TypeKind.STRUCT, tag="S")
        init = Identifier(L, C, name="a")
        gen._lower_initializer(ct, init, "@b", False)
        movs = [i for i in gen.instructions if i.op == "mov"]
        assert len(movs) >= 1
        assert movs[-1].result == "@b"


class TestArrayDispatchStub:
    """Non-string array types should now work via the general path (task 3.2)."""

    def test_int_array_emits_store_index(self):
        ctx = _make_sema_ctx()
        gen = _make_ir_gen(ctx)
        ct = CArrayType(kind=TypeKind.ARRAY, element=IntegerType(kind=TypeKind.INT), size=5)
        init = Initializer(L, C, elements=[
            (None, IntLiteral(L, C, value=1)),
            (None, IntLiteral(L, C, value=2)),
        ])
        gen._lower_initializer(ct, init, "@arr", False)
        ops = [ins.op for ins in gen.instructions]
        # 2 provided + 3 zero-filled = 5 store_index
        assert ops.count("store_index") == 5


class TestStructDispatchStub:
    """Struct/union Initializer should dispatch to _lower_struct_init."""

    def test_struct_init_emits_store_members(self):
        layout = _make_struct_layout("S", 8)
        ctx = _make_sema_ctx(layouts={"struct S": layout})
        gen = _make_ir_gen(ctx)
        ct = CStructType(kind=TypeKind.STRUCT, tag="S")
        init = Initializer(L, C, elements=[
            (None, IntLiteral(L, C, value=1)),
            (None, IntLiteral(L, C, value=2)),
        ])
        gen._lower_initializer(ct, init, "@s", False)
        ops = [ins.op for ins in gen.instructions]
        # Two scalar members → two store_member instructions
        assert ops.count("store_member") == 2
        # Verify member names
        member_names = [ins.operand2 for ins in gen.instructions if ins.op == "store_member"]
        assert member_names == ["x", "y"]

    def test_union_init_initializes_first_member(self):
        layout = _make_struct_layout("U", 4, kind="union")
        ctx = _make_sema_ctx(layouts={"union U": layout})
        gen = _make_ir_gen(ctx)
        ct = CStructType(kind=TypeKind.UNION, tag="U")
        init = Initializer(L, C, elements=[
            (None, IntLiteral(L, C, value=1)),
        ])
        gen._lower_initializer(ct, init, "@u", False)
        stores = [i for i in gen.instructions if i.op == "store_member"]
        assert len(stores) == 1
        assert stores[0].operand2 == "x"
