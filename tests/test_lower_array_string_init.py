"""Tests for _lower_array_init string initialization path (task 3.1).

Verifies:
- char s[6] = "hello" emits correct byte stores + NUL + zero-fill
- char s[] = "hello" infers size = 6 (len+1)
- char s[10] = "hi" zero-fills remaining bytes
- char s[] = {"hello"} unwraps braces
- unsigned char array + string literal works
- String too long for fixed-size array raises IRGenError
- Non-string array init still raises NotImplementedError (tasks 3.2/3.3)
- _extract_string_literal helper returns correct results
"""

import pytest
from unittest.mock import MagicMock
from pycc.ir import IRGenerator, IRInstruction, IRGenError
from pycc.types import (
    TypeKind, IntegerType,
    ArrayType as CArrayType,
)
from pycc.ast_nodes import (
    StringLiteral, Initializer, IntLiteral,
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


class TestCharArrayStringInit:
    """char s[N] = "..." should emit byte stores."""

    def test_fixed_size_exact(self):
        """char s[6] = "hello" → 5 char bytes + NUL."""
        ctx = _make_sema_ctx()
        gen = _make_ir_gen(ctx)
        char_ct = IntegerType(kind=TypeKind.CHAR)
        ct = CArrayType(kind=TypeKind.ARRAY, element=char_ct, size=6)
        init = StringLiteral(L, C, value="hello")
        gen._lower_array_init(ct, init, "@s")
        assert len(gen.instructions) == 6
        expected = [ord('h'), ord('e'), ord('l'), ord('l'), ord('o'), 0]
        for i, instr in enumerate(gen.instructions):
            assert instr.op == "store_index"
            assert instr.result == f"${expected[i]}"
            assert instr.operand1 == "@s"
            assert instr.operand2 == f"${i}"
            assert instr.label == "char"

    def test_fixed_size_with_zero_fill(self):
        """char s[10] = "hi" → 'h','i',NUL + 7 zeros."""
        ctx = _make_sema_ctx()
        gen = _make_ir_gen(ctx)
        char_ct = IntegerType(kind=TypeKind.CHAR)
        ct = CArrayType(kind=TypeKind.ARRAY, element=char_ct, size=10)
        init = StringLiteral(L, C, value="hi")
        gen._lower_array_init(ct, init, "@s")
        assert len(gen.instructions) == 10
        expected = [ord('h'), ord('i'), 0, 0, 0, 0, 0, 0, 0, 0]
        for i, instr in enumerate(gen.instructions):
            assert instr.op == "store_index"
            assert instr.result == f"${expected[i]}"
            assert instr.operand2 == f"${i}"

    def test_inferred_size(self):
        """char s[] = "hello" → size inferred as 6."""
        ctx = _make_sema_ctx()
        gen = _make_ir_gen(ctx)
        char_ct = IntegerType(kind=TypeKind.CHAR)
        ct = CArrayType(kind=TypeKind.ARRAY, element=char_ct, size=None)
        init = StringLiteral(L, C, value="hello")
        gen._lower_array_init(ct, init, "@s")
        assert len(gen.instructions) == 6
        assert gen.instructions[5].result == "$0"

    def test_empty_string(self):
        """char s[1] = "" → just NUL."""
        ctx = _make_sema_ctx()
        gen = _make_ir_gen(ctx)
        char_ct = IntegerType(kind=TypeKind.CHAR)
        ct = CArrayType(kind=TypeKind.ARRAY, element=char_ct, size=1)
        init = StringLiteral(L, C, value="")
        gen._lower_array_init(ct, init, "@s")
        assert len(gen.instructions) == 1
        assert gen.instructions[0].result == "$0"

    def test_empty_string_inferred(self):
        """char s[] = "" → size = 1, just NUL."""
        ctx = _make_sema_ctx()
        gen = _make_ir_gen(ctx)
        char_ct = IntegerType(kind=TypeKind.CHAR)
        ct = CArrayType(kind=TypeKind.ARRAY, element=char_ct, size=None)
        init = StringLiteral(L, C, value="")
        gen._lower_array_init(ct, init, "@s")
        assert len(gen.instructions) == 1
        assert gen.instructions[0].result == "$0"

    def test_braces_wrapped_string(self):
        """char s[] = {"hello"} → unwrap braces, same as bare string."""
        ctx = _make_sema_ctx()
        gen = _make_ir_gen(ctx)
        char_ct = IntegerType(kind=TypeKind.CHAR)
        ct = CArrayType(kind=TypeKind.ARRAY, element=char_ct, size=None)
        inner = StringLiteral(L, C, value="hello")
        init = Initializer(L, C, elements=[(None, inner)])
        gen._lower_array_init(ct, init, "@s")
        assert len(gen.instructions) == 6
        expected = [ord('h'), ord('e'), ord('l'), ord('l'), ord('o'), 0]
        for i, instr in enumerate(gen.instructions):
            assert instr.result == f"${expected[i]}"

    def test_string_too_long_raises(self):
        """char s[3] = "hello" → error (6 > 3)."""
        ctx = _make_sema_ctx()
        gen = _make_ir_gen(ctx)
        char_ct = IntegerType(kind=TypeKind.CHAR)
        ct = CArrayType(kind=TypeKind.ARRAY, element=char_ct, size=3)
        init = StringLiteral(L, C, value="hello")
        with pytest.raises(IRGenError, match="too long"):
            gen._lower_array_init(ct, init, "@s")

    def test_unsigned_char_array(self):
        """unsigned char s[4] = "abc" → works same as char."""
        ctx = _make_sema_ctx()
        gen = _make_ir_gen(ctx)
        uchar_ct = IntegerType(kind=TypeKind.CHAR, is_unsigned=True)
        ct = CArrayType(kind=TypeKind.ARRAY, element=uchar_ct, size=4)
        init = StringLiteral(L, C, value="abc")
        gen._lower_array_init(ct, init, "@s")
        assert len(gen.instructions) == 4
        expected = [ord('a'), ord('b'), ord('c'), 0]
        for i, instr in enumerate(gen.instructions):
            assert instr.result == f"${expected[i]}"


class TestExtractStringLiteral:
    """_extract_string_literal helper tests."""

    def test_bare_string_literal(self):
        gen = _make_ir_gen()
        sl = StringLiteral(L, C, value="test")
        assert gen._extract_string_literal(sl) is sl

    def test_braces_wrapped(self):
        gen = _make_ir_gen()
        sl = StringLiteral(L, C, value="test")
        init = Initializer(L, C, elements=[(None, sl)])
        assert gen._extract_string_literal(init) is sl

    def test_non_string_returns_none(self):
        gen = _make_ir_gen()
        init = Initializer(L, C, elements=[
            (None, IntLiteral(L, C, value=1)),
            (None, IntLiteral(L, C, value=2)),
        ])
        assert gen._extract_string_literal(init) is None

    def test_int_literal_returns_none(self):
        gen = _make_ir_gen()
        assert gen._extract_string_literal(IntLiteral(L, C, value=42)) is None

    def test_multi_element_initializer_returns_none(self):
        gen = _make_ir_gen()
        sl = StringLiteral(L, C, value="test")
        init = Initializer(L, C, elements=[
            (None, sl),
            (None, IntLiteral(L, C, value=0)),
        ])
        assert gen._extract_string_literal(init) is None


class TestNonStringArrayFallthrough:
    """Non-string array init should now work via the general path (task 3.2)."""

    def test_int_array_emits_store_index(self):
        ctx = _make_sema_ctx()
        gen = _make_ir_gen(ctx)
        int_ct = IntegerType(kind=TypeKind.INT)
        ct = CArrayType(kind=TypeKind.ARRAY, element=int_ct, size=3)
        init = Initializer(L, C, elements=[
            (None, IntLiteral(L, C, value=1)),
        ])
        gen._lower_array_init(ct, init, "@arr")
        ops = [ins.op for ins in gen.instructions]
        # Should emit store_index for element 0 (value=1) and zero-fill for elements 1,2
        assert ops.count("store_index") == 3
