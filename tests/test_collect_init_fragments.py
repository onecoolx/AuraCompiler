"""Unit tests for _collect_init_fragments recursive initializer collection."""
import struct
import pytest

from pycc.ir import IRGenerator, ResolvedType, InitFragment, _FlatInitIterator
from pycc.ast_nodes import (
    Initializer, IntLiteral, FloatLiteral, StringLiteral,
    Identifier, LabelAddress, Cast, UnaryOp, Type, Designator,
)

# Default line/column for test AST nodes
L, C = 0, 0


# ---------------------------------------------------------------------------
# AST node constructors with default location
# ---------------------------------------------------------------------------

def _int_lit(v):
    return IntLiteral(line=L, column=C, value=v)

def _float_lit(v):
    return FloatLiteral(line=L, column=C, value=v)

def _str_lit(v):
    return StringLiteral(line=L, column=C, value=v)

def _ident(name):
    return Identifier(line=L, column=C, name=name)

def _label_addr(name):
    return LabelAddress(line=L, column=C, label_name=name)

def _unary(op, operand):
    return UnaryOp(line=L, column=C, operator=op, operand=operand)

def _cast(ty, expr):
    return Cast(line=L, column=C, type=ty, expression=expr)

def _init_list(*exprs):
    """Create an Initializer with positional elements."""
    return Initializer(line=L, column=C, elements=[(None, e) for e in exprs])

def _desig_member(name):
    return Designator(line=L, column=C, member=name)

def _desig_index(idx):
    return Designator(line=L, column=C, index=_int_lit(idx))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ir_gen(sema_ctx=None):
    """Create an IRGenerator with optional sema_ctx."""
    gen = IRGenerator()
    gen._sema_ctx = sema_ctx
    gen._enum_constants = {}
    gen._fn_name = "test_fn"
    return gen


def _scalar(name, size, fmt, mask, is_float=False):
    return ResolvedType(
        kind="scalar", name=name, size=size,
        pack_format=fmt, pack_mask=mask, is_float=is_float
    )

def _int_type():
    return _scalar("int", 4, "<I", 0xFFFFFFFF)

def _float_type():
    return _scalar("float", 4, "<f", None, is_float=True)

def _double_type():
    return _scalar("double", 8, "<d", None, is_float=True)

def _char_type():
    return _scalar("char", 1, "<B", 0xFF)

def _long_type():
    return _scalar("long", 8, "<Q", 0xFFFFFFFFFFFFFFFF)

def _pointer_type(name="int*"):
    return ResolvedType(kind="pointer", name=name, size=8)

def _array_type(elem_type, length):
    return ResolvedType(
        kind="array", name=f"{elem_type.name}[{length}]",
        size=elem_type.size * length,
        element_type=elem_type, array_length=length
    )

def _struct_type(name, size, members):
    """members: [(name, offset, size, ResolvedType), ...]"""
    return ResolvedType(kind="struct", name=name, size=size, members=members)

def _union_type(name, size, members):
    """members: [(name, offset, size, ResolvedType), ...]"""
    return ResolvedType(kind="union", name=name, size=size, members=members)


# ---------------------------------------------------------------------------
# Tests: Scalar fragments
# ---------------------------------------------------------------------------

class TestScalarFragments:
    def test_int_literal(self):
        gen = _make_ir_gen()
        frags = gen._collect_init_fragments(_int_type(), _int_lit(42), 0)
        assert frags is not None
        assert len(frags) == 1
        f = frags[0]
        assert f.kind == "int"
        assert f.offset == 0
        assert f.size == 4
        assert f.value == struct.pack("<I", 42)

    def test_int_with_offset(self):
        gen = _make_ir_gen()
        frags = gen._collect_init_fragments(_int_type(), _int_lit(100), 16)
        assert frags is not None
        assert frags[0].offset == 16

    def test_negative_int(self):
        gen = _make_ir_gen()
        expr = _unary("-", _int_lit(1))
        frags = gen._collect_init_fragments(_int_type(), expr, 0)
        assert frags is not None
        assert frags[0].value == struct.pack("<I", 0xFFFFFFFF)

    def test_float_literal(self):
        gen = _make_ir_gen()
        frags = gen._collect_init_fragments(_float_type(), _float_lit(3.14), 0)
        assert frags is not None
        assert frags[0].kind == "float"
        assert frags[0].value == struct.pack("<f", 3.14)

    def test_double_literal(self):
        gen = _make_ir_gen()
        frags = gen._collect_init_fragments(_double_type(), _float_lit(2.718), 0)
        assert frags is not None
        assert frags[0].kind == "float"
        assert frags[0].size == 8
        assert frags[0].value == struct.pack("<d", 2.718)

    def test_int_to_float_promotion(self):
        gen = _make_ir_gen()
        frags = gen._collect_init_fragments(_float_type(), _int_lit(1), 0)
        assert frags is not None
        assert frags[0].kind == "float"
        assert frags[0].value == struct.pack("<f", 1.0)

    def test_scalar_in_braces(self):
        gen = _make_ir_gen()
        init = _init_list(_int_lit(7))
        frags = gen._collect_init_fragments(_int_type(), init, 0)
        assert frags is not None
        assert frags[0].value == struct.pack("<I", 7)

    def test_non_constant_returns_none(self):
        gen = _make_ir_gen()
        frags = gen._collect_init_fragments(_int_type(), _ident("x"), 0)
        assert frags is None


# ---------------------------------------------------------------------------
# Tests: Pointer fragments
# ---------------------------------------------------------------------------

class TestPointerFragments:
    def test_string_literal(self):
        gen = _make_ir_gen()
        frags = gen._collect_init_fragments(_pointer_type("char*"), _str_lit("hello"), 0)
        assert frags is not None
        assert len(frags) == 1
        assert frags[0].kind == "string"
        assert frags[0].value == "hello"
        assert frags[0].size == 8

    def test_symbol_identifier(self):
        gen = _make_ir_gen()
        frags = gen._collect_init_fragments(_pointer_type("void*"), _ident("malloc"), 0)
        assert frags is not None
        assert frags[0].kind == "symbol"
        assert frags[0].value == "malloc"

    def test_null_pointer(self):
        gen = _make_ir_gen()
        frags = gen._collect_init_fragments(_pointer_type("int*"), _int_lit(0), 0)
        assert frags is not None
        assert frags[0].kind == "null"
        assert frags[0].value == 0

    def test_address_of_symbol(self):
        gen = _make_ir_gen()
        expr = _unary("&", _ident("global_var"))
        frags = gen._collect_init_fragments(_pointer_type("int*"), expr, 0)
        assert frags is not None
        assert frags[0].kind == "symbol"
        assert frags[0].value == "global_var"

    def test_label_address(self):
        gen = _make_ir_gen()
        frags = gen._collect_init_fragments(_pointer_type("void*"), _label_addr("target"), 0)
        assert frags is not None
        assert frags[0].kind == "symbol"
        assert frags[0].value == ".Luser_test_fn_target"

    def test_cast_null(self):
        gen = _make_ir_gen()
        ty = Type(line=L, column=C, base="void", is_pointer=True)
        expr = _cast(ty, _int_lit(0))
        frags = gen._collect_init_fragments(_pointer_type("void*"), expr, 0)
        assert frags is not None
        assert frags[0].kind == "null"

    def test_non_constant_pointer_returns_none(self):
        gen = _make_ir_gen()
        from pycc.ast_nodes import FunctionCall
        expr = FunctionCall(line=L, column=C, function=_ident("get_ptr"), arguments=[])
        frags = gen._collect_init_fragments(_pointer_type("int*"), expr, 0)
        assert frags is None


# ---------------------------------------------------------------------------
# Tests: Array fragments
# ---------------------------------------------------------------------------

class TestArrayFragments:
    def test_int_array(self):
        gen = _make_ir_gen()
        rtype = _array_type(_int_type(), 3)
        init = _init_list(_int_lit(1), _int_lit(2), _int_lit(3))
        frags = gen._collect_init_fragments(rtype, init, 0)
        assert frags is not None
        assert len(frags) == 3
        assert frags[0].offset == 0
        assert frags[0].value == struct.pack("<I", 1)
        assert frags[1].offset == 4
        assert frags[1].value == struct.pack("<I", 2)
        assert frags[2].offset == 8
        assert frags[2].value == struct.pack("<I", 3)

    def test_int_array_partial_zero_fill(self):
        gen = _make_ir_gen()
        rtype = _array_type(_int_type(), 4)
        init = _init_list(_int_lit(10), _int_lit(20))
        frags = gen._collect_init_fragments(rtype, init, 0)
        assert frags is not None
        assert len(frags) == 4
        assert frags[0].value == struct.pack("<I", 10)
        assert frags[1].value == struct.pack("<I", 20)
        assert frags[2].kind == "zero"
        assert frags[2].offset == 8
        assert frags[2].size == 4
        assert frags[3].kind == "zero"
        assert frags[3].offset == 12

    def test_char_array_from_string(self):
        gen = _make_ir_gen()
        rtype = _array_type(_char_type(), 6)
        init = _init_list(_str_lit("hi"))
        frags = gen._collect_init_fragments(rtype, init, 0)
        assert frags is not None
        assert len(frags) == 1
        expected = struct.pack("<6B", ord('h'), ord('i'), 0, 0, 0, 0)
        assert frags[0].value == expected
        assert frags[0].size == 6

    def test_pointer_array(self):
        gen = _make_ir_gen()
        rtype = _array_type(_pointer_type("char*"), 3)
        init = _init_list(_str_lit("foo"), _ident("bar"), _int_lit(0))
        frags = gen._collect_init_fragments(rtype, init, 0)
        assert frags is not None
        assert len(frags) == 3
        assert frags[0].kind == "string"
        assert frags[0].offset == 0
        assert frags[1].kind == "symbol"
        assert frags[1].offset == 8
        assert frags[2].kind == "null"
        assert frags[2].offset == 16

    def test_designated_array(self):
        gen = _make_ir_gen()
        rtype = _array_type(_int_type(), 5)
        init = Initializer(line=L, column=C, elements=[
            (_desig_index(1), _int_lit(10)),
            (_desig_index(3), _int_lit(30)),
        ])
        frags = gen._collect_init_fragments(rtype, init, 0)
        assert frags is not None
        # [0]=zero, [1]=10, [2]=zero, [3]=30, [4]=zero
        assert frags[0].kind == "zero"
        assert frags[0].offset == 0
        assert frags[1].value == struct.pack("<I", 10)
        assert frags[1].offset == 4
        assert frags[2].kind == "zero"
        assert frags[2].offset == 8
        assert frags[3].value == struct.pack("<I", 30)
        assert frags[3].offset == 12
        assert frags[4].kind == "zero"
        assert frags[4].offset == 16


# ---------------------------------------------------------------------------
# Tests: Struct fragments
# ---------------------------------------------------------------------------

class TestStructFragments:
    def test_simple_struct(self):
        gen = _make_ir_gen()
        rtype = _struct_type("struct Point", 8, [
            ("x", 0, 4, _int_type()),
            ("y", 4, 4, _int_type()),
        ])
        init = _init_list(_int_lit(10), _int_lit(20))
        frags = gen._collect_init_fragments(rtype, init, 0)
        assert frags is not None
        assert len(frags) == 2
        assert frags[0].offset == 0
        assert frags[0].value == struct.pack("<I", 10)
        assert frags[1].offset == 4
        assert frags[1].value == struct.pack("<I", 20)

    def test_struct_with_padding(self):
        gen = _make_ir_gen()
        # struct { char c; int x; } — c at 0, padding 1-3, x at 4, size 8
        rtype = _struct_type("struct Padded", 8, [
            ("c", 0, 1, _char_type()),
            ("x", 4, 4, _int_type()),
        ])
        init = _init_list(_int_lit(65), _int_lit(100))
        frags = gen._collect_init_fragments(rtype, init, 0)
        assert frags is not None
        # Find the padding fragment
        pad = [f for f in frags if f.kind == "zero" and f.offset == 1]
        assert len(pad) == 1
        assert pad[0].size == 3

    def test_struct_partial_init(self):
        gen = _make_ir_gen()
        rtype = _struct_type("struct S", 12, [
            ("a", 0, 4, _int_type()),
            ("b", 4, 4, _int_type()),
            ("c", 8, 4, _int_type()),
        ])
        init = _init_list(_int_lit(1))
        frags = gen._collect_init_fragments(rtype, init, 0)
        assert frags is not None
        assert frags[0].value == struct.pack("<I", 1)
        zero_frags = [f for f in frags if f.kind == "zero"]
        assert len(zero_frags) == 2

    def test_struct_with_pointer_member(self):
        gen = _make_ir_gen()
        rtype = _struct_type("struct Hooks", 24, [
            ("alloc", 0, 8, _pointer_type("void*")),
            ("free", 8, 8, _pointer_type("void*")),
            ("realloc", 16, 8, _pointer_type("void*")),
        ])
        init = _init_list(_ident("malloc"), _ident("free"), _ident("realloc"))
        frags = gen._collect_init_fragments(rtype, init, 0)
        assert frags is not None
        assert len(frags) == 3
        assert frags[0].kind == "symbol"
        assert frags[0].value == "malloc"
        assert frags[1].kind == "symbol"
        assert frags[1].value == "free"
        assert frags[2].kind == "symbol"
        assert frags[2].value == "realloc"

    def test_designated_struct(self):
        gen = _make_ir_gen()
        rtype = _struct_type("struct S", 12, [
            ("a", 0, 4, _int_type()),
            ("b", 4, 4, _int_type()),
            ("c", 8, 4, _int_type()),
        ])
        init = Initializer(line=L, column=C, elements=[
            (_desig_member("c"), _int_lit(99)),
            (_desig_member("a"), _int_lit(11)),
        ])
        frags = gen._collect_init_fragments(rtype, init, 0)
        assert frags is not None
        int_frags = [f for f in frags if f.kind == "int"]
        assert len(int_frags) == 2
        a_frag = next(f for f in int_frags if f.offset == 0)
        c_frag = next(f for f in int_frags if f.offset == 8)
        assert a_frag.value == struct.pack("<I", 11)
        assert c_frag.value == struct.pack("<I", 99)

    def test_struct_tail_padding(self):
        gen = _make_ir_gen()
        # struct { int x; char c; } — x at 0, c at 4, size 8 (3 bytes tail)
        rtype = _struct_type("struct Tail", 8, [
            ("x", 0, 4, _int_type()),
            ("c", 4, 1, _char_type()),
        ])
        init = _init_list(_int_lit(1), _int_lit(65))
        frags = gen._collect_init_fragments(rtype, init, 0)
        assert frags is not None
        tail = [f for f in frags if f.kind == "zero" and f.offset == 5]
        assert len(tail) == 1
        assert tail[0].size == 3


# ---------------------------------------------------------------------------
# Tests: Union fragments
# ---------------------------------------------------------------------------

class TestUnionFragments:
    def test_union_first_member(self):
        gen = _make_ir_gen()
        rtype = _union_type("union U", 8, [
            ("i", 0, 4, _int_type()),
            ("d", 0, 8, _double_type()),
        ])
        init = _init_list(_int_lit(42))
        frags = gen._collect_init_fragments(rtype, init, 0)
        assert frags is not None
        int_frag = next(f for f in frags if f.kind == "int")
        assert int_frag.value == struct.pack("<I", 42)
        zero_frag = next(f for f in frags if f.kind == "zero")
        assert zero_frag.offset == 4
        assert zero_frag.size == 4


# ---------------------------------------------------------------------------
# Tests: Nested types
# ---------------------------------------------------------------------------

class TestNestedTypes:
    def test_array_of_structs(self):
        gen = _make_ir_gen()
        elem_type = _struct_type("struct Pair", 8, [
            ("a", 0, 4, _int_type()),
            ("b", 4, 4, _int_type()),
        ])
        rtype = _array_type(elem_type, 2)
        init = _init_list(
            _init_list(_int_lit(1), _int_lit(2)),
            _init_list(_int_lit(3), _int_lit(4)),
        )
        frags = gen._collect_init_fragments(rtype, init, 0)
        assert frags is not None
        int_frags = [f for f in frags if f.kind == "int"]
        assert len(int_frags) == 4
        assert int_frags[0].offset == 0
        assert int_frags[0].value == struct.pack("<I", 1)
        assert int_frags[1].offset == 4
        assert int_frags[1].value == struct.pack("<I", 2)
        assert int_frags[2].offset == 8
        assert int_frags[2].value == struct.pack("<I", 3)
        assert int_frags[3].offset == 12
        assert int_frags[3].value == struct.pack("<I", 4)

    def test_struct_with_array_member(self):
        gen = _make_ir_gen()
        arr_type = _array_type(_int_type(), 3)
        rtype = _struct_type("struct WithArr", 16, [
            ("id", 0, 4, _int_type()),
            ("data", 4, 12, arr_type),
        ])
        init = _init_list(
            _int_lit(99),
            _init_list(_int_lit(10), _int_lit(20), _int_lit(30)),
        )
        frags = gen._collect_init_fragments(rtype, init, 0)
        assert frags is not None
        int_frags = [f for f in frags if f.kind == "int"]
        assert len(int_frags) == 4
        assert int_frags[0].offset == 0
        assert int_frags[0].value == struct.pack("<I", 99)
        assert int_frags[1].offset == 4
        assert int_frags[2].offset == 8
        assert int_frags[3].offset == 12


# ---------------------------------------------------------------------------
# Tests: Brace elision
# ---------------------------------------------------------------------------

class TestBraceElision:
    def test_struct_brace_elision(self):
        """struct { int a; int b; } arr[2] = {1, 2, 3, 4}"""
        gen = _make_ir_gen()
        elem_type = _struct_type("struct Pair", 8, [
            ("a", 0, 4, _int_type()),
            ("b", 4, 4, _int_type()),
        ])
        rtype = _array_type(elem_type, 2)
        init = _init_list(
            _int_lit(1), _int_lit(2), _int_lit(3), _int_lit(4),
        )
        frags = gen._collect_init_fragments(rtype, init, 0)
        assert frags is not None
        int_frags = [f for f in frags if f.kind == "int"]
        assert len(int_frags) == 4
        assert int_frags[0].value == struct.pack("<I", 1)
        assert int_frags[1].value == struct.pack("<I", 2)
        assert int_frags[2].value == struct.pack("<I", 3)
        assert int_frags[3].value == struct.pack("<I", 4)

    def test_array_brace_elision_in_struct(self):
        """struct { int x; int arr[2]; } = {1, 2, 3}"""
        gen = _make_ir_gen()
        arr_type = _array_type(_int_type(), 2)
        rtype = _struct_type("struct S", 12, [
            ("x", 0, 4, _int_type()),
            ("arr", 4, 8, arr_type),
        ])
        init = _init_list(_int_lit(1), _int_lit(2), _int_lit(3))
        frags = gen._collect_init_fragments(rtype, init, 0)
        assert frags is not None
        int_frags = [f for f in frags if f.kind == "int"]
        assert len(int_frags) == 3
        assert int_frags[0].offset == 0
        assert int_frags[0].value == struct.pack("<I", 1)
        assert int_frags[1].offset == 4
        assert int_frags[1].value == struct.pack("<I", 2)
        assert int_frags[2].offset == 8
        assert int_frags[2].value == struct.pack("<I", 3)


# ---------------------------------------------------------------------------
# Tests: _FlatInitIterator
# ---------------------------------------------------------------------------

class TestFlatInitIterator:
    def test_basic_consume(self):
        elems = [(None, _int_lit(1)), (None, _int_lit(2))]
        it = _FlatInitIterator(elems)
        assert not it.exhausted()
        e1 = it.consume()
        assert isinstance(e1, IntLiteral) and e1.value == 1
        e2 = it.consume()
        assert isinstance(e2, IntLiteral) and e2.value == 2
        assert it.exhausted()

    def test_next_for_scalar(self):
        elems = [(None, _int_lit(5))]
        it = _FlatInitIterator(elems)
        result = it.next_for_type(_int_type())
        assert isinstance(result, IntLiteral) and result.value == 5

    def test_next_for_aggregate_braced(self):
        inner = _init_list(_int_lit(1), _int_lit(2))
        elems = [(None, inner)]
        it = _FlatInitIterator(elems)
        rtype = _struct_type("struct S", 8, [
            ("a", 0, 4, _int_type()),
            ("b", 4, 4, _int_type()),
        ])
        result = it.next_for_type(rtype)
        assert isinstance(result, Initializer)
        assert result is inner

    def test_next_for_aggregate_elision(self):
        elems = [
            (None, _int_lit(1)),
            (None, _int_lit(2)),
            (None, _int_lit(3)),
        ]
        it = _FlatInitIterator(elems)
        rtype = _struct_type("struct S", 8, [
            ("a", 0, 4, _int_type()),
            ("b", 4, 4, _int_type()),
        ])
        result = it.next_for_type(rtype)
        assert isinstance(result, Initializer)
        assert len(result.elements) == 2
        assert not it.exhausted()
        remaining = it.consume()
        assert isinstance(remaining, IntLiteral) and remaining.value == 3


# ---------------------------------------------------------------------------
# Tests: Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_none_rtype_returns_none(self):
        gen = _make_ir_gen()
        frags = gen._collect_init_fragments(None, _int_lit(0), 0)
        assert frags is None

    def test_empty_initializer_list_for_struct(self):
        gen = _make_ir_gen()
        rtype = _struct_type("struct S", 8, [
            ("a", 0, 4, _int_type()),
            ("b", 4, 4, _int_type()),
        ])
        init = Initializer(line=L, column=C, elements=[])
        frags = gen._collect_init_fragments(rtype, init, 0)
        assert frags is not None
        assert all(f.kind == "zero" for f in frags)

    def test_base_offset_propagation(self):
        gen = _make_ir_gen()
        rtype = _array_type(_int_type(), 2)
        init = _init_list(_int_lit(1), _int_lit(2))
        frags = gen._collect_init_fragments(rtype, init, 100)
        assert frags is not None
        assert frags[0].offset == 100
        assert frags[1].offset == 104
