"""Tests for codegen CType-based member access migration (task 5.4).

Verifies that load_member, load_member_ptr, store_member, store_member_ptr
correctly use CType from result_type and meta["member_ctype"] to determine
load/store widths, with string-based fallback when CType is unavailable.
"""

import pytest
from pycc.types import (
    CType, TypeKind, IntegerType, FloatType, PointerType, StructType,
    ArrayType, Qualifiers, TypedSymbolTable, type_sizeof,
)
from pycc.codegen import CodeGenerator
from pycc.ir import IRInstruction


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
                 member_types=None, member_decl_types=None, align=1,
                 bit_fields=None, _bf_info=None):
        self.size = size
        self.member_offsets = member_offsets or {}
        self.member_sizes = member_sizes or {}
        self.member_types = member_types or {}
        self.member_decl_types = member_decl_types or {}
        self.align = align
        self.bit_fields = bit_fields
        self._bf_info = _bf_info


def _make_codegen_with_struct(struct_tag="struct Point", members=None):
    """Create a CodeGenerator with a struct layout and symbol table.

    members: list of (name, offset, size, type_str, ctype) tuples
    """
    if members is None:
        members = [
            ("x", 0, 4, "int", IntegerType(kind=TypeKind.INT)),
            ("y", 4, 4, "int", IntegerType(kind=TypeKind.INT)),
        ]
    layout = FakeLayout(
        size=sum(m[2] for m in members),
        member_offsets={m[0]: m[1] for m in members},
        member_sizes={m[0]: m[2] for m in members},
        member_types={m[0]: m[3] for m in members},
    )
    sema_ctx = FakeSemaCtx(layouts={struct_tag: layout})
    sym_table = TypedSymbolTable(sema_ctx)
    # Register a local struct variable @s
    sym_table.push_scope()
    sym_table.insert("@s", StructType(kind=TypeKind.STRUCT, tag=struct_tag.replace("struct ", "")))
    # Register a pointer-to-struct temp %t0
    sym_table.insert("%t0", PointerType(kind=TypeKind.POINTER,
                                         pointee=StructType(kind=TypeKind.STRUCT,
                                                            tag=struct_tag.replace("struct ", ""))))
    cg = CodeGenerator(optimize=False, sema_ctx=sema_ctx, sym_table=sym_table)
    cg._var_types = {}
    # Simulate function context
    cg._locals = {"@s": -16}
    cg._arrays = {}
    cg._member_offsets = {}
    cg._spill_capacity = 4096
    cg._spill_used = 0
    cg._fn_name = "test"
    cg.assembly_lines = []
    cg._string_pool = {}
    cg._string_counter = 0
    cg._float_pool = {}
    cg._float_counter = 0
    cg._functions = set()
    cg._ptr_step_bytes = {}
    cg._hidden_ret_ptr_off = 0
    return cg



# ---------------------------------------------------------------------------
# Tests: load_member with result_type
# ---------------------------------------------------------------------------

class TestLoadMemberCType:
    """Verify load_member uses result_type for load width when available."""

    def test_load_member_int_uses_movl(self):
        """load_member with result_type=INT should emit movl (4-byte load)."""
        cg = _make_codegen_with_struct()
        ins = IRInstruction(
            op="load_member", result="%t1", operand1="@s", operand2="x",
            result_type=IntegerType(kind=TypeKind.INT),
        )
        cg._emit_ins(ins)
        asm = "\n".join(cg.assembly_lines)
        assert "movl (%rax), %eax" in asm

    def test_load_member_char_uses_movsbl(self):
        """load_member with result_type=CHAR (signed) should emit movsbl."""
        members = [("c", 0, 1, "char", IntegerType(kind=TypeKind.CHAR))]
        cg = _make_codegen_with_struct("struct S", members)
        ins = IRInstruction(
            op="load_member", result="%t1", operand1="@s", operand2="c",
            result_type=IntegerType(kind=TypeKind.CHAR, is_unsigned=False),
        )
        cg._emit_ins(ins)
        asm = "\n".join(cg.assembly_lines)
        # Signed char: sign-extend
        assert "movsb" in asm.lower() or "movsbq" in asm.lower()

    def test_load_member_unsigned_char_uses_movzbl(self):
        """load_member with result_type=unsigned CHAR should emit movzbl."""
        members = [("uc", 0, 1, "unsigned char",
                     IntegerType(kind=TypeKind.CHAR, is_unsigned=True))]
        cg = _make_codegen_with_struct("struct S", members)
        ins = IRInstruction(
            op="load_member", result="%t1", operand1="@s", operand2="uc",
            result_type=IntegerType(kind=TypeKind.CHAR, is_unsigned=True),
        )
        cg._emit_ins(ins)
        asm = "\n".join(cg.assembly_lines)
        # Unsigned char: zero-extend
        assert "movb (%rax), %al" in asm
        assert "movzbq" in asm

    def test_load_member_short_uses_movw(self):
        """load_member with result_type=SHORT should emit movw (2-byte load)."""
        members = [("s", 0, 2, "short", IntegerType(kind=TypeKind.SHORT))]
        cg = _make_codegen_with_struct("struct S", members)
        ins = IRInstruction(
            op="load_member", result="%t1", operand1="@s", operand2="s",
            result_type=IntegerType(kind=TypeKind.SHORT),
        )
        cg._emit_ins(ins)
        asm = "\n".join(cg.assembly_lines)
        assert "movw (%rax), %ax" in asm

    def test_load_member_pointer_uses_movq(self):
        """load_member with result_type=POINTER should emit movq (8-byte load)."""
        members = [("p", 0, 8, "int *",
                     PointerType(kind=TypeKind.POINTER,
                                 pointee=IntegerType(kind=TypeKind.INT)))]
        cg = _make_codegen_with_struct("struct S", members)
        ins = IRInstruction(
            op="load_member", result="%t1", operand1="@s", operand2="p",
            result_type=PointerType(kind=TypeKind.POINTER,
                                    pointee=IntegerType(kind=TypeKind.INT)),
        )
        cg._emit_ins(ins)
        asm = "\n".join(cg.assembly_lines)
        assert "movq (%rax), %rax" in asm

    def test_load_member_fallback_without_result_type(self):
        """load_member without result_type falls back to _resolve_member."""
        cg = _make_codegen_with_struct()
        ins = IRInstruction(
            op="load_member", result="%t1", operand1="@s", operand2="x",
            result_type=None,
        )
        cg._emit_ins(ins)
        asm = "\n".join(cg.assembly_lines)
        # Should still produce valid assembly via string fallback
        assert "(%rax)" in asm


# ---------------------------------------------------------------------------
# Tests: load_member_ptr with result_type
# ---------------------------------------------------------------------------

class TestLoadMemberPtrCType:
    """Verify load_member_ptr uses result_type for load width."""

    def test_load_member_ptr_int_uses_movl(self):
        """load_member_ptr with result_type=INT should emit movl."""
        cg = _make_codegen_with_struct()
        # Seed %t0 as a pointer in _var_types for base address loading
        cg._var_types["%t0"] = "struct Point*"
        ins = IRInstruction(
            op="load_member_ptr", result="%t1", operand1="%t0", operand2="x",
            result_type=IntegerType(kind=TypeKind.INT),
        )
        cg._emit_ins(ins)
        asm = "\n".join(cg.assembly_lines)
        assert "movl (%rax), %eax" in asm


# ---------------------------------------------------------------------------
# Tests: store_member with member_ctype
# ---------------------------------------------------------------------------

class TestStoreMemberCType:
    """Verify store_member uses meta['member_ctype'] for store width."""

    def test_store_member_int_uses_movl(self):
        """store_member with member_ctype=INT should emit movl (4-byte store)."""
        cg = _make_codegen_with_struct()
        cg._locals["%t1"] = -24
        ins = IRInstruction(
            op="store_member", result="%t1", operand1="@s", operand2="x",
            meta={"member_ctype": IntegerType(kind=TypeKind.INT)},
        )
        cg._emit_ins(ins)
        asm = "\n".join(cg.assembly_lines)
        assert "movl %ecx, (%rax)" in asm

    def test_store_member_char_uses_movb(self):
        """store_member with member_ctype=CHAR should emit movb (1-byte store)."""
        members = [("c", 0, 1, "char", IntegerType(kind=TypeKind.CHAR))]
        cg = _make_codegen_with_struct("struct S", members)
        cg._locals["%t1"] = -24
        ins = IRInstruction(
            op="store_member", result="%t1", operand1="@s", operand2="c",
            meta={"member_ctype": IntegerType(kind=TypeKind.CHAR)},
        )
        cg._emit_ins(ins)
        asm = "\n".join(cg.assembly_lines)
        assert "movb %cl, (%rax)" in asm

    def test_store_member_fallback_without_member_ctype(self):
        """store_member without member_ctype falls back to _resolve_member."""
        cg = _make_codegen_with_struct()
        cg._locals["%t1"] = -24
        ins = IRInstruction(
            op="store_member", result="%t1", operand1="@s", operand2="x",
            meta={},
        )
        cg._emit_ins(ins)
        asm = "\n".join(cg.assembly_lines)
        # Should still produce valid assembly via string fallback
        assert "(%rax)" in asm


# ---------------------------------------------------------------------------
# Tests: store_member_ptr with member_ctype
# ---------------------------------------------------------------------------

class TestStoreMemberPtrCType:
    """Verify store_member_ptr uses meta['member_ctype'] for store width."""

    def test_store_member_ptr_int_uses_movl(self):
        """store_member_ptr with member_ctype=INT should emit movl."""
        cg = _make_codegen_with_struct()
        cg._var_types["%t0"] = "struct Point*"
        cg._locals["%t1"] = -24
        ins = IRInstruction(
            op="store_member_ptr", result="%t1", operand1="%t0", operand2="x",
            meta={"member_ctype": IntegerType(kind=TypeKind.INT)},
        )
        cg._emit_ins(ins)
        asm = "\n".join(cg.assembly_lines)
        assert "movl %ecx, (%rax)" in asm


# ---------------------------------------------------------------------------
# Tests: _ctype_is_unsigned_char helper
# ---------------------------------------------------------------------------

class TestCtypeIsUnsignedChar:
    """Verify the _ctype_is_unsigned_char helper method."""

    def test_unsigned_char_returns_true(self):
        cg = CodeGenerator(optimize=False)
        ct = IntegerType(kind=TypeKind.CHAR, is_unsigned=True)
        assert cg._ctype_is_unsigned_char(ct) is True

    def test_signed_char_returns_false(self):
        cg = CodeGenerator(optimize=False)
        ct = IntegerType(kind=TypeKind.CHAR, is_unsigned=False)
        assert cg._ctype_is_unsigned_char(ct) is False

    def test_int_returns_false(self):
        cg = CodeGenerator(optimize=False)
        ct = IntegerType(kind=TypeKind.INT)
        assert cg._ctype_is_unsigned_char(ct) is False

    def test_none_returns_false(self):
        cg = CodeGenerator(optimize=False)
        assert cg._ctype_is_unsigned_char(None) is False

    def test_pointer_returns_false(self):
        cg = CodeGenerator(optimize=False)
        ct = PointerType(kind=TypeKind.POINTER)
        assert cg._ctype_is_unsigned_char(ct) is False
