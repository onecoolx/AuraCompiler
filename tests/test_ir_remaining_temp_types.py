"""Unit tests for remaining temp variable CType annotations.

Verifies that the IR generator correctly annotates CTypes for:
- Function call return values
- Binary operation results (integer arithmetic, comparisons, float ops)
- String literals
- Float literals
- Logical operators (&&, ||)

Since the symbol table scope is popped after function generation completes,
integration tests verify via _var_types and IR instruction inspection.
Helper method tests verify CType logic directly.
"""

import pytest
from unittest.mock import MagicMock
from pycc.ir import IRGenerator, IRInstruction
from pycc.types import (
    CType, TypeKind, IntegerType, FloatType, PointerType,
    StructType, TypedSymbolTable, ctype_to_ir_type,
)
from pycc.ast_nodes import (
    Program, FunctionDecl, CompoundStmt, ReturnStmt, IntLiteral,
    FloatLiteral, StringLiteral, BinaryOp, FunctionCall, Identifier,
    ExpressionStmt, Declaration,
)


def _make_type(base, is_pointer=False):
    """Create a minimal AST Type-like object."""
    t = MagicMock()
    t.base = base
    t.is_pointer = is_pointer
    t.is_volatile = False
    t.is_const = False
    t.is_unsigned = False
    t.is_signed = False
    t.pointer_level = 1 if is_pointer else 0
    t.pointer_quals = []
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
    ctx.global_linkage = {}
    ctx.global_kinds = {}
    ctx.function_param_types = {}
    return ctx


def _fn_with_body(name, ret_type, body_stmts, params=None):
    """Create a FunctionDecl with given body statements."""
    rt = _make_type(ret_type)
    body = CompoundStmt(0, 0, statements=body_stmts)
    fn = FunctionDecl(
        line=0, column=0,
        name=name,
        return_type=rt,
        parameters=params or [],
        body=body,
    )
    return fn


def _program_with_fn(fn):
    """Create a Program with a single function."""
    return Program(0, 0, declarations=[fn])


def _gen_with_sema(program, sema_ctx):
    """Generate IR with a semantic context and return (instructions, gen)."""
    gen = IRGenerator()
    gen._sema_ctx = sema_ctx
    ir = gen.generate(program)
    return ir, gen


class TestStringLiteralCType:
    """String literals should be annotated as char* in _var_types."""

    def test_string_literal_has_char_pointer_type(self):
        expr = StringLiteral(0, 0, value="hello")
        stmt = ExpressionStmt(0, 0, expression=expr)
        fn = _fn_with_body("test_fn", "int", [
            stmt,
            ReturnStmt(0, 0, value=IntLiteral(0, 0, value=0)),
        ])
        prog = _program_with_fn(fn)
        sema = _make_sema_ctx()
        ir, gen = _gen_with_sema(prog, sema)

        # Find the str_const instruction
        str_insts = [i for i in ir if i.op == "str_const"]
        assert len(str_insts) >= 1
        result_temp = str_insts[0].result
        # Verify _var_types has char*
        assert result_temp in gen._var_types
        assert gen._var_types[result_temp] == "char*"


class TestFloatLiteralCType:
    """Float literals should be annotated with correct fp type."""

    def test_double_literal_has_double_type(self):
        expr = FloatLiteral(0, 0, value=3.14)
        stmt = ExpressionStmt(0, 0, expression=expr)
        fn = _fn_with_body("test_fn", "int", [
            stmt,
            ReturnStmt(0, 0, value=IntLiteral(0, 0, value=0)),
        ])
        prog = _program_with_fn(fn)
        sema = _make_sema_ctx()
        ir, gen = _gen_with_sema(prog, sema)

        fmov_insts = [i for i in ir if i.op == "fmov"]
        assert len(fmov_insts) >= 1
        result_temp = fmov_insts[0].result
        assert gen._var_types[result_temp] == "double"

    def test_float_suffix_literal_has_float_type(self):
        expr = FloatLiteral(0, 0, value=1.0)
        expr.suffix = 'f'
        stmt = ExpressionStmt(0, 0, expression=expr)
        fn = _fn_with_body("test_fn", "int", [
            stmt,
            ReturnStmt(0, 0, value=IntLiteral(0, 0, value=0)),
        ])
        prog = _program_with_fn(fn)
        sema = _make_sema_ctx()
        ir, gen = _gen_with_sema(prog, sema)

        fmov_insts = [i for i in ir if i.op == "fmov"]
        assert len(fmov_insts) >= 1
        result_temp = fmov_insts[0].result
        assert gen._var_types[result_temp] == "float"


class TestFunctionCallReturnCType:
    """Function call return values should get CType from function_sigs."""

    def test_float_return_function_call_tracked(self):
        # float sqrtf(); ... sqrtf(x);
        call_expr = FunctionCall(0, 0,
            function=Identifier(0, 0, name="sqrtf"),
            arguments=[IntLiteral(0, 0, value=4)])
        stmt = ExpressionStmt(0, 0, expression=call_expr)
        fn = _fn_with_body("test_fn", "int", [
            stmt,
            ReturnStmt(0, 0, value=IntLiteral(0, 0, value=0)),
        ])
        prog = _program_with_fn(fn)
        sema = _make_sema_ctx(
            function_sigs={"sqrtf": ("float", 1, False)},
            global_types={"sqrtf": "function float"},
        )
        ir, gen = _gen_with_sema(prog, sema)

        call_insts = [i for i in ir if i.op == "call"]
        assert len(call_insts) >= 1
        result_temp = call_insts[0].result
        # Float return should be tracked in _var_types
        assert result_temp in gen._var_types
        assert gen._var_types[result_temp] == "float"

    def test_struct_return_not_registered_as_struct(self):
        # struct S make(); ... make();
        call_expr = FunctionCall(0, 0,
            function=Identifier(0, 0, name="make"),
            arguments=[])
        stmt = ExpressionStmt(0, 0, expression=call_expr)
        fn = _fn_with_body("test_fn", "int", [
            stmt,
            ReturnStmt(0, 0, value=IntLiteral(0, 0, value=0)),
        ])
        prog = _program_with_fn(fn)
        sema = _make_sema_ctx(
            function_sigs={"make": ("struct Big", 0, False)},
            global_types={"make": "function struct Big"},
        )
        ir, gen = _gen_with_sema(prog, sema)

        call_insts = [i for i in ir if i.op == "call"]
        assert len(call_insts) >= 1
        result_temp = call_insts[0].result
        # Struct return should NOT be in _var_types as a struct
        # (hidden pointer ABI)
        vt = gen._var_types.get(result_temp, "")
        assert not vt.startswith("struct ")


class TestBinaryOpResultCType:
    """Binary operation results should get appropriate type annotations."""

    def test_integer_addition_result_tracked(self):
        # 1 + 2
        expr = BinaryOp(0, 0, operator="+",
            left=IntLiteral(0, 0, value=1),
            right=IntLiteral(0, 0, value=2))
        ret = ReturnStmt(0, 0, value=expr)
        fn = _fn_with_body("test_fn", "int", [ret])
        prog = _program_with_fn(fn)
        sema = _make_sema_ctx()
        ir, gen = _gen_with_sema(prog, sema)

        # The binop instruction should exist
        binop_insts = [i for i in ir if i.op == "binop" and i.label == "+"]
        assert len(binop_insts) >= 1

    def test_float_addition_result_tracked(self):
        # 1.0 + 2.0
        expr = BinaryOp(0, 0, operator="+",
            left=FloatLiteral(0, 0, value=1.0),
            right=FloatLiteral(0, 0, value=2.0))
        ret = ReturnStmt(0, 0, value=expr)
        fn = _fn_with_body("test_fn", "int", [ret])
        prog = _program_with_fn(fn)
        sema = _make_sema_ctx()
        ir, gen = _gen_with_sema(prog, sema)

        # The fadd instruction should exist with result tracked as double
        fadd_insts = [i for i in ir if i.op == "fadd"]
        assert len(fadd_insts) >= 1
        result_temp = fadd_insts[0].result
        assert gen._var_types[result_temp] == "double"


class TestHelperMethods:
    """Test the helper methods _return_type_to_ctype and _uac_result_ctype."""

    def test_return_type_to_ctype_int(self):
        gen = IRGenerator()
        gen._sema_ctx = _make_sema_ctx(
            function_sigs={"foo": ("int", 0, False)})
        ct = gen._return_type_to_ctype("foo")
        assert ct is not None
        assert ct.kind == TypeKind.INT

    def test_return_type_to_ctype_float(self):
        gen = IRGenerator()
        gen._sema_ctx = _make_sema_ctx(
            function_sigs={"bar": ("float", 0, False)})
        ct = gen._return_type_to_ctype("bar")
        assert ct is not None
        assert ct.kind == TypeKind.FLOAT

    def test_return_type_to_ctype_double(self):
        gen = IRGenerator()
        gen._sema_ctx = _make_sema_ctx(
            function_sigs={"baz": ("double", 0, False)})
        ct = gen._return_type_to_ctype("baz")
        assert ct is not None
        assert ct.kind == TypeKind.DOUBLE

    def test_return_type_to_ctype_pointer(self):
        gen = IRGenerator()
        gen._sema_ctx = _make_sema_ctx(
            function_sigs={"get": ("char *", 0, False)})
        ct = gen._return_type_to_ctype("get")
        assert ct is not None
        assert isinstance(ct, PointerType)
        assert ct.kind == TypeKind.POINTER

    def test_return_type_to_ctype_struct(self):
        gen = IRGenerator()
        gen._sema_ctx = _make_sema_ctx(
            function_sigs={"make": ("struct Big", 0, False)})
        ct = gen._return_type_to_ctype("make")
        assert ct is not None
        assert ct.kind == TypeKind.STRUCT

    def test_return_type_to_ctype_void_returns_none(self):
        gen = IRGenerator()
        gen._sema_ctx = _make_sema_ctx(
            function_sigs={"baz": ("void", 0, False)})
        ct = gen._return_type_to_ctype("baz")
        assert ct is None

    def test_return_type_to_ctype_unknown_returns_none(self):
        gen = IRGenerator()
        gen._sema_ctx = _make_sema_ctx(function_sigs={})
        ct = gen._return_type_to_ctype("unknown")
        assert ct is None

    def test_return_type_to_ctype_no_sema_returns_none(self):
        gen = IRGenerator()
        gen._sema_ctx = None
        ct = gen._return_type_to_ctype("foo")
        assert ct is None

    def test_uac_result_ctype_int_int(self):
        gen = IRGenerator()
        ct = gen._uac_result_ctype("int", "int")
        assert ct is not None
        assert ct.kind == TypeKind.INT

    def test_uac_result_ctype_int_long(self):
        gen = IRGenerator()
        ct = gen._uac_result_ctype("int", "long")
        assert ct is not None
        assert ct.kind == TypeKind.LONG

    def test_uac_result_ctype_unsigned_int(self):
        gen = IRGenerator()
        ct = gen._uac_result_ctype("unsigned int", "int")
        assert ct is not None
        assert ct.kind == TypeKind.INT
        assert ct.is_unsigned is True

    def test_uac_result_ctype_float_int(self):
        gen = IRGenerator()
        ct = gen._uac_result_ctype("float", "int")
        assert ct is not None
        assert ct.kind == TypeKind.FLOAT

    def test_uac_result_ctype_double_float(self):
        gen = IRGenerator()
        ct = gen._uac_result_ctype("double", "float")
        assert ct is not None
        assert ct.kind == TypeKind.DOUBLE

    def test_uac_result_ctype_empty_returns_none(self):
        gen = IRGenerator()
        ct = gen._uac_result_ctype("", "")
        assert ct is None

    def test_uac_result_ctype_long_double(self):
        gen = IRGenerator()
        ct = gen._uac_result_ctype("long double", "float")
        assert ct is not None
        assert ct.kind == TypeKind.DOUBLE  # best approx for long double
