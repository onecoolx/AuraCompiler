"""Tests for CodeGenerator sym_table integration.

Verifies that CodeGenerator accepts sym_table parameter and that
_get_type helper correctly uses the symbol table.
"""
from __future__ import annotations

import pytest
from pycc.codegen import CodeGenerator
from pycc.types import (
    CType, TypeKind, IntegerType, FloatType, PointerType,
    TypedSymbolTable, _str_to_ctype,
)


class TestCodeGeneratorSymTable:
    """CodeGenerator sym_table constructor and _get_type tests."""

    def test_constructor_accepts_sym_table(self):
        """sym_table parameter is stored on the instance."""
        st = TypedSymbolTable()
        cg = CodeGenerator(optimize=False, sym_table=st)
        assert cg._sym_table is st

    def test_constructor_sym_table_defaults_none(self):
        """sym_table defaults to None when not provided."""
        cg = CodeGenerator(optimize=False)
        assert cg._sym_table is None

    def test_get_type_from_sym_table(self):
        """_get_type returns CType from symbol table when available."""
        st = TypedSymbolTable()
        int_ct = IntegerType(kind=TypeKind.INT)
        st.insert("@x", int_ct)
        cg = CodeGenerator(optimize=False, sym_table=st)
        result = cg._get_type("@x")
        assert result is not None
        assert result.kind == TypeKind.INT

    def test_get_type_returns_none_when_not_in_sym_table(self):
        """_get_type returns None when sym_table has no entry."""
        st = TypedSymbolTable()
        cg = CodeGenerator(optimize=False, sym_table=st)
        result = cg._get_type("@y")
        assert result is None

    def test_get_type_sym_table_correct_type(self):
        """_get_type returns the correct type from sym_table."""
        st = TypedSymbolTable()
        float_ct = FloatType(kind=TypeKind.FLOAT)
        st.insert("@z", float_ct)
        cg = CodeGenerator(optimize=False, sym_table=st)
        result = cg._get_type("@z")
        assert result is not None
        assert result.kind == TypeKind.FLOAT

    def test_get_type_no_sym_table_returns_none(self):
        """_get_type returns None when sym_table is None."""
        cg = CodeGenerator(optimize=False, sym_table=None)
        result = cg._get_type("@a")
        assert result is None

    def test_get_type_returns_none_for_unknown(self):
        """_get_type returns None when symbol is not found anywhere."""
        st = TypedSymbolTable()
        cg = CodeGenerator(optimize=False, sym_table=st)
        result = cg._get_type("@unknown")
        assert result is None


class TestCompilerPipelineSymTable:
    """Verify compiler.py passes sym_table through the pipeline."""

    def test_get_ir_returns_tuple(self):
        """get_ir returns (ir_list, sym_table) tuple."""
        from pycc.compiler import Compiler
        comp = Compiler(optimize=False)
        code = "int main(void) { return 0; }"
        tokens = comp.get_tokens(code)
        ast = comp.get_ast(tokens)
        sema_ctx, _ = comp.analyze_semantics(ast)
        result = comp.get_ir(ast, sema_ctx=sema_ctx)
        assert isinstance(result, tuple)
        assert len(result) == 2
        ir, sym_table = result
        assert isinstance(ir, list)

    def test_get_assembly_accepts_sym_table(self):
        """get_assembly accepts and passes sym_table to CodeGenerator."""
        from pycc.compiler import Compiler
        comp = Compiler(optimize=False)
        code = "int main(void) { return 42; }"
        tokens = comp.get_tokens(code)
        ast = comp.get_ast(tokens)
        sema_ctx, _ = comp.analyze_semantics(ast)
        ir, sym_table = comp.get_ir(ast, sema_ctx=sema_ctx)
        asm = comp.get_assembly(ir, sema_ctx=sema_ctx, sym_table=sym_table)
        assert isinstance(asm, str)
        assert len(asm) > 0
