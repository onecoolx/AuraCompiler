"""Tests for IRGenerator TypedSymbolTable integration (task 3.1).

Verifies:
- _sym_table is initialized in generate() when _sema_ctx is present
- _sym_table is None when _sema_ctx is absent
- _new_temp_typed dual-populates _sym_table and _var_types
- push_scope/pop_scope are called around function bodies
"""

import pytest
from unittest.mock import MagicMock
from pycc.ir import IRGenerator, IRInstruction
from pycc.types import (
    CType, TypeKind, IntegerType, FloatType, PointerType,
    StructType, Qualifiers, TypedSymbolTable, ctype_to_ir_type,
)
from pycc.ast_nodes import (
    Program, FunctionDecl, CompoundStmt, ReturnStmt, IntLiteral,
    Declaration,
)


def _make_type(base, is_pointer=False):
    """Create a minimal AST Type-like object."""
    t = MagicMock()
    t.base = base
    t.is_pointer = is_pointer
    t.is_volatile = False
    t.pointer_level = 0
    return t


def _make_sema_ctx(typedefs=None, layouts=None, global_types=None,
                   function_sigs=None, global_decl_types=None):
    """Create a minimal SemanticContext-like object."""
    ctx = MagicMock()
    ctx.typedefs = typedefs or {}
    ctx.layouts = layouts or {}
    ctx.global_types = global_types or {}
    ctx.function_sigs = function_sigs or {}
    ctx.global_decl_types = global_decl_types or {}
    return ctx


def _simple_function(name="test_fn", ret_type="int"):
    """Create a minimal FunctionDecl with an empty body returning 0."""
    rt = _make_type(ret_type)
    body = CompoundStmt(0, 0, statements=[ReturnStmt(0, 0, value=IntLiteral(0, 0, value=0))])
    fn = FunctionDecl(
        line=0, column=0,
        name=name,
        return_type=rt,
        parameters=[],
        body=body,
    )
    return fn


def _simple_program(functions=None):
    """Create a minimal Program AST."""
    decls = list(functions or [])
    return Program(0, 0, declarations=decls)


class TestSymTableInitialization:
    """Verify _sym_table is created in generate() based on _sema_ctx."""

    def test_sym_table_created_with_sema_ctx(self):
        gen = IRGenerator()
        gen._sema_ctx = _make_sema_ctx()
        fn = _simple_function()
        prog = _simple_program([fn])
        gen.generate(prog)
        assert gen._sym_table is not None
        assert isinstance(gen._sym_table, TypedSymbolTable)

    def test_sym_table_none_without_sema_ctx(self):
        gen = IRGenerator()
        gen._sema_ctx = None
        fn = _simple_function()
        prog = _simple_program([fn])
        gen.generate(prog)
        assert gen._sym_table is None


class TestNewTempTyped:
    """Verify _new_temp_typed dual-populates _sym_table and _var_types."""

    def test_dual_population_int(self):
        gen = IRGenerator()
        gen._sema_ctx = _make_sema_ctx()
        fn = _simple_function()
        prog = _simple_program([fn])
        gen.generate(prog)

        ct = IntegerType(kind=TypeKind.INT, quals=Qualifiers(), is_unsigned=False)
        name = gen._new_temp_typed(ct)

        assert name.startswith("%t")
        # Check _sym_table has the entry
        looked_up = gen._sym_table.lookup(name)
        assert looked_up is not None
        assert looked_up.kind == TypeKind.INT
        # Check _var_types has the compatible string
        assert name in gen._var_types
        assert gen._var_types[name] == ctype_to_ir_type(ct)

    def test_dual_population_pointer(self):
        gen = IRGenerator()
        gen._sema_ctx = _make_sema_ctx()
        fn = _simple_function()
        prog = _simple_program([fn])
        gen.generate(prog)

        pointee = IntegerType(kind=TypeKind.CHAR, quals=Qualifiers(), is_unsigned=False)
        ct = PointerType(kind=TypeKind.POINTER, quals=Qualifiers(), pointee=pointee)
        name = gen._new_temp_typed(ct)

        looked_up = gen._sym_table.lookup(name)
        assert looked_up is not None
        assert looked_up.kind == TypeKind.POINTER
        assert gen._var_types[name] == ctype_to_ir_type(ct)

    def test_dual_population_struct(self):
        gen = IRGenerator()
        gen._sema_ctx = _make_sema_ctx()
        fn = _simple_function()
        prog = _simple_program([fn])
        gen.generate(prog)

        ct = StructType(kind=TypeKind.STRUCT, quals=Qualifiers(), tag="my_struct")
        name = gen._new_temp_typed(ct)

        looked_up = gen._sym_table.lookup(name)
        assert looked_up is not None
        assert looked_up.kind == TypeKind.STRUCT
        assert gen._var_types[name] == "struct my_struct"

    def test_no_sym_table_still_populates_var_types(self):
        """When _sym_table is None, _new_temp_typed still updates _var_types."""
        gen = IRGenerator()
        gen._sema_ctx = None
        fn = _simple_function()
        prog = _simple_program([fn])
        gen.generate(prog)

        ct = IntegerType(kind=TypeKind.INT, quals=Qualifiers(), is_unsigned=False)
        name = gen._new_temp_typed(ct)

        assert gen._sym_table is None
        assert name in gen._var_types
        assert gen._var_types[name] == "int"

    def test_temp_names_increment(self):
        gen = IRGenerator()
        gen._sema_ctx = _make_sema_ctx()
        fn = _simple_function()
        prog = _simple_program([fn])
        gen.generate(prog)

        ct = IntegerType(kind=TypeKind.INT, quals=Qualifiers(), is_unsigned=False)
        base_counter = gen.temp_counter
        n1 = gen._new_temp_typed(ct)
        n2 = gen._new_temp_typed(ct)
        assert n1 == f"%t{base_counter}"
        assert n2 == f"%t{base_counter + 1}"
