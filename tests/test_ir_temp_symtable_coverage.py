"""Unit tests verifying that temporary variable type registrations
write to _sym_table (TypedSymbolTable) in addition to _var_types.

All temp variable type registrations must have _sym_table coverage.
"""
import pytest
from pycc.types import (
    TypedSymbolTable, IntegerType, FloatType, PointerType,
    TypeKind, CType, ctype_to_ir_type,
)


def _make_ir_gen(tmp_path):
    """Create a minimal IRGenerator instance for testing."""
    from pycc.ir import IRGenerator
    from pycc.ast_nodes import FunctionDecl, CompoundStmt
    # Minimal function to trigger IR gen setup
    gen = IRGenerator.__new__(IRGenerator)
    gen.instructions = []
    gen.temp_counter = 0
    gen._var_types = {}
    gen._sym_table = TypedSymbolTable()
    gen._scope_stack = [{}]
    gen._sema_ctx = None
    gen._fn_name = "test"
    gen._fn_ret_type = None
    gen._local_ast_types = {}
    gen._ptr_step_bytes = {}
    gen._enum_constants = {}
    return gen


class TestEnsureU32SymTableCoverage:
    """_ensure_u32 should register unsigned int CType in _sym_table."""

    def test_ensure_u32_registers_in_sym_table(self, tmp_path):
        gen = _make_ir_gen(tmp_path)
        t = gen._ensure_u32("%t0")
        ct = gen._sym_table.lookup(t)
        assert ct is not None
        assert isinstance(ct, IntegerType)
        assert ct.kind == TypeKind.INT
        assert ct.is_unsigned is True


class TestEnsureU64SymTableCoverage:
    """_ensure_u64 should register unsigned long CType in _sym_table."""

    def test_ensure_u64_new_temp_registers_in_sym_table(self, tmp_path):
        gen = _make_ir_gen(tmp_path)
        t = gen._ensure_u64("$42")
        ct = gen._sym_table.lookup(t)
        assert ct is not None
        assert isinstance(ct, IntegerType)
        assert ct.kind == TypeKind.LONG
        assert ct.is_unsigned is True

    def test_ensure_u64_existing_temp_registers_in_sym_table(self, tmp_path):
        gen = _make_ir_gen(tmp_path)
        # Pre-create a temp
        existing = gen._new_temp()
        t = gen._ensure_u64(existing)
        assert t == existing  # should reuse
        ct = gen._sym_table.lookup(t)
        assert ct is not None
        assert isinstance(ct, IntegerType)
        assert ct.kind == TypeKind.LONG
        assert ct.is_unsigned is True


class TestNewTempTypedSymTableCoverage:
    """_new_temp_typed should register CType in _sym_table."""

    def test_float_type(self, tmp_path):
        gen = _make_ir_gen(tmp_path)
        ft = FloatType(kind=TypeKind.FLOAT)
        t = gen._new_temp_typed(ft)
        ct = gen._sym_table.lookup(t)
        assert ct is not None
        assert ct.kind == TypeKind.FLOAT

    def test_pointer_type(self, tmp_path):
        gen = _make_ir_gen(tmp_path)
        pt = PointerType(kind=TypeKind.POINTER,
                         pointee=IntegerType(kind=TypeKind.CHAR))
        t = gen._new_temp_typed(pt)
        ct = gen._sym_table.lookup(t)
        assert ct is not None
        assert isinstance(ct, PointerType)
        assert ct.pointee.kind == TypeKind.CHAR

    def test_integer_type(self, tmp_path):
        gen = _make_ir_gen(tmp_path)
        it = IntegerType(kind=TypeKind.INT, is_unsigned=False)
        t = gen._new_temp_typed(it)
        ct = gen._sym_table.lookup(t)
        assert ct is not None
        assert isinstance(ct, IntegerType)
        assert ct.is_unsigned is False
