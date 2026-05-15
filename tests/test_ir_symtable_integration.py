"""Tests for IRGenerator TypedSymbolTable integration.

Verifies:
- _sym_table is initialized in generate() when _sema_ctx is present
- _sym_table is None when _sema_ctx is absent
- _new_temp_typed populates _sym_table and _var_types
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
    """Verify _new_temp_typed populates _sym_table and _var_types."""

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


# ---- Parameter and local variable CType insertion ----

from pycc.types import ArrayType as CArrayType


def _make_param(name, base, is_pointer=False, pointer_level=0, is_unsigned=False,
                is_signed=False, is_volatile=False):
    """Create a minimal parameter Declaration-like object."""
    t = MagicMock()
    t.base = base
    t.is_pointer = is_pointer
    t.pointer_level = pointer_level if pointer_level else (1 if is_pointer else 0)
    t.is_volatile = is_volatile
    t.is_unsigned = is_unsigned
    t.is_signed = is_signed
    t.is_const = False
    t.pointer_quals = []
    p = MagicMock()
    p.name = name
    p.type = t
    return p


def _fn_with_params(params, body_stmts=None):
    """Create a FunctionDecl with given parameters."""
    rt = _make_type("int")
    stmts = body_stmts or [ReturnStmt(0, 0, value=IntLiteral(0, 0, value=0))]
    body = CompoundStmt(0, 0, statements=stmts)
    fn = FunctionDecl(
        line=0, column=0,
        name="test_fn",
        return_type=rt,
        parameters=params,
        body=body,
    )
    return fn


def _make_local_decl(name, base, is_pointer=False, pointer_level=0,
                     array_size=None, is_unsigned=False, is_signed=False,
                     initializer=None, storage_class=None, is_volatile=False):
    """Create a minimal local variable Declaration."""
    t = _make_type(base, is_pointer=is_pointer)
    t.pointer_level = pointer_level if pointer_level else (1 if is_pointer else 0)
    t.is_unsigned = is_unsigned
    t.is_signed = is_signed
    t.is_volatile = is_volatile
    t.is_const = False
    t.pointer_quals = []
    d = Declaration(
        line=0, column=0,
        name=name,
        type=t,
        initializer=initializer,
    )
    d.array_size = array_size
    d.array_dims = [array_size] if array_size is not None else None
    d.storage_class = storage_class
    return d


class TestParamCTypeInsertion:
    """Verify parameters are inserted into _sym_table during _gen_function.

    Note: _gen_function pops the function scope at the end, so we verify
    by patching pop_scope to capture the scope contents before they are lost.
    """

    def _generate_and_capture_scope(self, params, sema_ctx=None):
        """Generate IR and capture the function scope before it is popped."""
        fn = _fn_with_params(params)
        gen = IRGenerator()
        gen._sema_ctx = sema_ctx or _make_sema_ctx()
        captured = {}
        orig_pop = gen.__class__._pop_scope

        def _capturing_pop(self_inner):
            # Before popping, snapshot the symbol table scope
            if self_inner._sym_table and self_inner._sym_table._scope_stack:
                captured.update(self_inner._sym_table._scope_stack[-1])
            orig_pop(self_inner)

        gen._pop_scope = lambda: _capturing_pop(gen)
        gen.generate(_simple_program([fn]))
        return gen, captured

    def test_int_param(self):
        params = [_make_param("x", "int")]
        gen, scope = self._generate_and_capture_scope(params)
        assert "@x" in scope
        assert scope["@x"].kind == TypeKind.INT

    def test_pointer_param(self):
        params = [_make_param("p", "int", is_pointer=True)]
        gen, scope = self._generate_and_capture_scope(params)
        assert "@p" in scope
        assert scope["@p"].kind == TypeKind.POINTER
        assert scope["@p"].pointee.kind == TypeKind.INT

    def test_char_param(self):
        params = [_make_param("c", "char")]
        gen, scope = self._generate_and_capture_scope(params)
        assert "@c" in scope
        assert scope["@c"].kind == TypeKind.CHAR

    def test_struct_pointer_param(self):
        params = [_make_param("sp", "struct node", is_pointer=True)]
        gen, scope = self._generate_and_capture_scope(params)
        assert "@sp" in scope
        assert scope["@sp"].kind == TypeKind.POINTER
        assert scope["@sp"].pointee.kind == TypeKind.STRUCT
        assert scope["@sp"].pointee.tag == "node"

    def test_multiple_params(self):
        params = [
            _make_param("a", "int"),
            _make_param("b", "long"),
            _make_param("c", "char", is_pointer=True),
        ]
        gen, scope = self._generate_and_capture_scope(params)
        assert scope["@a"].kind == TypeKind.INT
        assert scope["@b"].kind == TypeKind.LONG
        assert scope["@c"].kind == TypeKind.POINTER
        assert scope["@c"].pointee.kind == TypeKind.CHAR

    def test_param_var_types_sync(self):
        """Verify _var_types and _sym_table are both populated for params."""
        params = [_make_param("x", "int")]
        gen, scope = self._generate_and_capture_scope(params)
        assert "@x" in gen._var_types
        assert "@x" in scope

    def test_no_sym_table_without_sema_ctx(self):
        """When _sema_ctx is None, params are only in _var_types."""
        params = [_make_param("x", "int")]
        fn = _fn_with_params(params)
        gen = IRGenerator()
        gen._sema_ctx = None
        gen.generate(_simple_program([fn]))
        assert gen._sym_table is None
        assert "@x" in gen._var_types


class TestLocalVarCTypeInsertion:
    """Verify local variable declarations are inserted into _sym_table."""

    def _generate_and_capture_scope(self, body_stmts, sema_ctx=None):
        """Generate IR and capture the function scope before it is popped."""
        fn = _fn_with_params([], body_stmts=body_stmts)
        gen = IRGenerator()
        gen._sema_ctx = sema_ctx or _make_sema_ctx()
        captured = {}
        orig_pop = gen.__class__._pop_scope

        def _capturing_pop(self_inner):
            # Capture all scope levels before popping
            if self_inner._sym_table and self_inner._sym_table._scope_stack:
                for s in self_inner._sym_table._scope_stack:
                    captured.update(s)
            orig_pop(self_inner)

        gen._pop_scope = lambda: _capturing_pop(gen)
        gen.generate(_simple_program([fn]))
        return gen, captured

    def test_int_local(self):
        decl = _make_local_decl("x", "int")
        body_stmts = [decl, ReturnStmt(0, 0, value=IntLiteral(0, 0, value=0))]
        gen, scope = self._generate_and_capture_scope(body_stmts)
        assert "@x" in scope
        assert scope["@x"].kind == TypeKind.INT

    def test_pointer_local(self):
        decl = _make_local_decl("p", "char", is_pointer=True)
        body_stmts = [decl, ReturnStmt(0, 0, value=IntLiteral(0, 0, value=0))]
        gen, scope = self._generate_and_capture_scope(body_stmts)
        assert "@p" in scope
        assert scope["@p"].kind == TypeKind.POINTER
        assert scope["@p"].pointee.kind == TypeKind.CHAR

    def test_array_local(self):
        decl = _make_local_decl("arr", "int", array_size=10)
        body_stmts = [decl, ReturnStmt(0, 0, value=IntLiteral(0, 0, value=0))]
        gen, scope = self._generate_and_capture_scope(body_stmts)
        assert "@arr" in scope
        ct = scope["@arr"]
        assert ct.kind == TypeKind.ARRAY
        assert isinstance(ct, CArrayType)
        assert ct.size == 10
        assert ct.element.kind == TypeKind.INT

    def test_struct_local(self):
        from pycc.semantics import StructLayout
        layout = StructLayout(
            kind="struct",
            name="point",
            member_offsets={"x": 0, "y": 4},
            member_sizes={"x": 4, "y": 4},
            member_types={"x": "int", "y": "int"},
            member_decl_types={},
            size=8, align=4,
        )
        sema = _make_sema_ctx(layouts={"struct point": layout})
        decl = _make_local_decl("pt", "struct point")
        body_stmts = [decl, ReturnStmt(0, 0, value=IntLiteral(0, 0, value=0))]
        gen, scope = self._generate_and_capture_scope(body_stmts, sema_ctx=sema)
        assert "@pt" in scope
        ct = scope["@pt"]
        assert ct.kind == TypeKind.STRUCT
        assert ct.tag == "point"

    def test_local_var_types_sync(self):
        """Verify _var_types and _sym_table are both populated for locals."""
        decl = _make_local_decl("x", "int")
        body_stmts = [decl, ReturnStmt(0, 0, value=IntLiteral(0, 0, value=0))]
        gen, scope = self._generate_and_capture_scope(body_stmts)
        assert "@x" in gen._var_types
        assert "@x" in scope

    def test_typedef_param_resolved(self):
        """Verify typedef parameters are resolved to concrete types."""
        td_type = MagicMock()
        td_type.base = "int"
        td_type.is_pointer = False
        td_type.pointer_level = 0
        td_type.is_unsigned = False
        td_type.is_signed = False
        td_type.is_const = False
        td_type.is_volatile = False
        td_type.pointer_quals = []
        sema = _make_sema_ctx(typedefs={"myint": td_type})
        params = [_make_param("x", "myint")]
        fn = _fn_with_params(params)
        gen = IRGenerator()
        gen._sema_ctx = sema
        captured = {}
        orig_pop = gen.__class__._pop_scope

        def _capturing_pop(self_inner):
            if self_inner._sym_table and self_inner._sym_table._scope_stack:
                for s in self_inner._sym_table._scope_stack:
                    captured.update(s)
            orig_pop(self_inner)

        gen._pop_scope = lambda: _capturing_pop(gen)
        gen.generate(_simple_program([fn]))

        assert "@x" in captured
        ct = captured["@x"]
        # After typedef resolution, myint -> int
        assert ct.kind == TypeKind.INT
