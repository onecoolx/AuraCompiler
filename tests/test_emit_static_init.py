"""Unit tests for _emit_static_init top-level emission method."""
import struct
import pytest

from pycc.ir import IRGenerator, IRInstruction, ResolvedType, InitFragment
from pycc.ast_nodes import (
    Initializer, IntLiteral, FloatLiteral, StringLiteral,
    Identifier, LabelAddress, Cast, UnaryOp, Type, Designator,
)

# Default line/column for test AST nodes
L, C = 0, 0


def _blob_bytes(operand2):
    """Extract raw bytes from a gdef_blob operand2 string (strip 'blob:' prefix)."""
    if operand2.startswith("blob:"):
        return bytes.fromhex(operand2[5:])
    return bytes.fromhex(operand2)


# ---------------------------------------------------------------------------
# AST node constructors
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
# Type helpers
# ---------------------------------------------------------------------------

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
# IR Generator helper
# ---------------------------------------------------------------------------

def _make_ir_gen(sema_ctx=None):
    """Create an IRGenerator with minimal state for testing."""
    gen = IRGenerator()
    gen._sema_ctx = sema_ctx
    gen._enum_constants = {}
    gen._fn_name = "test_fn"
    gen.instructions = []
    return gen


# ---------------------------------------------------------------------------
# Tests: Single scalar → gdef
# ---------------------------------------------------------------------------

class TestSingleScalarGdef:
    def test_int_scalar(self):
        gen = _make_ir_gen()
        rtype = _int_type()
        result = gen._emit_static_init("my_int", rtype, _int_lit(42), "static")
        assert result is True
        assert len(gen.instructions) == 1
        instr = gen.instructions[0]
        assert instr.op == "gdef"
        assert instr.result == "@my_int"
        assert instr.operand1 == "int"
        assert instr.operand2 == "$42"
        assert instr.label == "static"

    def test_char_scalar(self):
        gen = _make_ir_gen()
        rtype = _char_type()
        result = gen._emit_static_init("ch", rtype, _int_lit(65), "")
        assert result is True
        instr = gen.instructions[0]
        assert instr.op == "gdef"
        assert instr.operand2 == "$65"

    def test_long_scalar(self):
        gen = _make_ir_gen()
        rtype = _long_type()
        result = gen._emit_static_init("big", rtype, _int_lit(0x123456789), "static")
        assert result is True
        instr = gen.instructions[0]
        assert instr.op == "gdef"
        assert instr.operand2 == "$4886718345"

    def test_negative_int(self):
        gen = _make_ir_gen()
        rtype = _int_type()
        # -1 as unsigned 32-bit = 0xFFFFFFFF = 4294967295
        result = gen._emit_static_init("neg", rtype, _unary("-", _int_lit(1)), "static")
        assert result is True
        instr = gen.instructions[0]
        assert instr.op == "gdef"
        assert instr.operand2 == "$4294967295"


# ---------------------------------------------------------------------------
# Tests: Single float → gdef_float
# ---------------------------------------------------------------------------

class TestSingleFloatGdefFloat:
    def test_float_scalar(self):
        gen = _make_ir_gen()
        rtype = _float_type()
        result = gen._emit_static_init("my_float", rtype, _float_lit(3.14), "static")
        assert result is True
        instr = gen.instructions[0]
        assert instr.op == "gdef_float"
        assert instr.result == "@my_float"
        assert instr.label == "static"
        assert instr.meta["fp_type"] == "float"
        # Value should be the float representation
        assert float(instr.operand1) == pytest.approx(3.14, rel=1e-5)

    def test_double_scalar(self):
        gen = _make_ir_gen()
        rtype = _double_type()
        result = gen._emit_static_init("my_double", rtype, _float_lit(2.718), "")
        assert result is True
        instr = gen.instructions[0]
        assert instr.op == "gdef_float"
        assert instr.meta["fp_type"] == "double"
        assert float(instr.operand1) == pytest.approx(2.718, rel=1e-10)


# ---------------------------------------------------------------------------
# Tests: Single pointer → gdef
# ---------------------------------------------------------------------------

class TestSinglePointerGdef:
    def test_string_pointer(self):
        gen = _make_ir_gen()
        rtype = _pointer_type("char*")
        result = gen._emit_static_init("msg", rtype, _str_lit("hello"), "static")
        assert result is True
        instr = gen.instructions[0]
        assert instr.op == "gdef"
        assert instr.result == "@msg"
        assert instr.operand2 == "=str:hello"

    def test_symbol_pointer(self):
        gen = _make_ir_gen()
        rtype = _pointer_type("void*")
        result = gen._emit_static_init("fp", rtype, _ident("malloc"), "static")
        assert result is True
        instr = gen.instructions[0]
        assert instr.op == "gdef"
        assert instr.operand2 == "malloc"

    def test_null_pointer(self):
        gen = _make_ir_gen()
        rtype = _pointer_type("int*")
        result = gen._emit_static_init("np", rtype, _int_lit(0), "static")
        assert result is True
        instr = gen.instructions[0]
        assert instr.op == "gdef"
        assert instr.operand2 == "$0"

    def test_address_of_pointer(self):
        gen = _make_ir_gen()
        rtype = _pointer_type("int*")
        result = gen._emit_static_init("ptr", rtype, _unary("&", _ident("global_var")), "")
        assert result is True
        instr = gen.instructions[0]
        assert instr.op == "gdef"
        assert instr.operand2 == "global_var"


# ---------------------------------------------------------------------------
# Tests: Pure scalar array → gdef_blob
# ---------------------------------------------------------------------------

class TestPureScalarBlob:
    def test_int_array(self):
        gen = _make_ir_gen()
        rtype = _array_type(_int_type(), 3)
        init = _init_list(_int_lit(1), _int_lit(2), _int_lit(3))
        result = gen._emit_static_init("arr", rtype, init, "static")
        assert result is True
        instr = gen.instructions[0]
        assert instr.op == "gdef_blob"
        assert instr.result == "@arr"
        assert instr.label == "static"
        # Verify blob content: 3 little-endian 32-bit ints
        blob_bytes = _blob_bytes(instr.operand2)
        assert len(blob_bytes) == 12
        assert struct.unpack_from("<I", blob_bytes, 0)[0] == 1
        assert struct.unpack_from("<I", blob_bytes, 4)[0] == 2
        assert struct.unpack_from("<I", blob_bytes, 8)[0] == 3

    def test_int_array_with_zero_fill(self):
        gen = _make_ir_gen()
        rtype = _array_type(_int_type(), 4)
        init = _init_list(_int_lit(10), _int_lit(20))
        result = gen._emit_static_init("arr", rtype, init, "")
        assert result is True
        instr = gen.instructions[0]
        assert instr.op == "gdef_blob"
        blob_bytes = _blob_bytes(instr.operand2)
        assert len(blob_bytes) == 16
        assert struct.unpack_from("<I", blob_bytes, 0)[0] == 10
        assert struct.unpack_from("<I", blob_bytes, 4)[0] == 20
        assert struct.unpack_from("<I", blob_bytes, 8)[0] == 0
        assert struct.unpack_from("<I", blob_bytes, 12)[0] == 0

    def test_struct_pure_scalars(self):
        gen = _make_ir_gen()
        # struct { int a; int b; } — size 8, no padding
        rtype = _struct_type("struct S", 8, [
            ("a", 0, 4, _int_type()),
            ("b", 4, 4, _int_type()),
        ])
        init = _init_list(_int_lit(100), _int_lit(200))
        result = gen._emit_static_init("s", rtype, init, "static")
        assert result is True
        instr = gen.instructions[0]
        assert instr.op == "gdef_blob"
        blob_bytes = _blob_bytes(instr.operand2)
        assert len(blob_bytes) == 8
        assert struct.unpack_from("<I", blob_bytes, 0)[0] == 100
        assert struct.unpack_from("<I", blob_bytes, 4)[0] == 200

    def test_struct_with_padding(self):
        gen = _make_ir_gen()
        # struct { char a; int b; } — a at 0, b at 4, size 8
        rtype = _struct_type("struct P", 8, [
            ("a", 0, 1, _char_type()),
            ("b", 4, 4, _int_type()),
        ])
        init = _init_list(_int_lit(65), _int_lit(100))
        result = gen._emit_static_init("p", rtype, init, "static")
        assert result is True
        instr = gen.instructions[0]
        assert instr.op == "gdef_blob"
        blob_bytes = _blob_bytes(instr.operand2)
        assert len(blob_bytes) == 8
        assert blob_bytes[0] == 65  # char 'A'
        assert blob_bytes[1:4] == b'\x00\x00\x00'  # padding
        assert struct.unpack_from("<I", blob_bytes, 4)[0] == 100

    def test_float_array(self):
        gen = _make_ir_gen()
        rtype = _array_type(_float_type(), 2)
        init = _init_list(_float_lit(1.0), _float_lit(2.0))
        result = gen._emit_static_init("farr", rtype, init, "static")
        assert result is True
        instr = gen.instructions[0]
        assert instr.op == "gdef_blob"
        blob_bytes = _blob_bytes(instr.operand2)
        assert len(blob_bytes) == 8
        assert struct.unpack_from("<f", blob_bytes, 0)[0] == pytest.approx(1.0)
        assert struct.unpack_from("<f", blob_bytes, 4)[0] == pytest.approx(2.0)


# ---------------------------------------------------------------------------
# Tests: Pointer array → gdef_ptr_array
# ---------------------------------------------------------------------------

class TestPointerArrayGdefPtrArray:
    def test_string_pointer_array(self):
        gen = _make_ir_gen()
        rtype = _array_type(_pointer_type("char*"), 3)
        init = _init_list(_str_lit("foo"), _str_lit("bar"), _str_lit("baz"))
        result = gen._emit_static_init("strs", rtype, init, "static")
        assert result is True
        instr = gen.instructions[0]
        assert instr.op == "gdef_ptr_array"
        assert instr.result == "@strs"
        entries = instr.meta["entries"]
        assert entries == [("string", "foo"), ("string", "bar"), ("string", "baz")]

    def test_symbol_pointer_array(self):
        gen = _make_ir_gen()
        rtype = _array_type(_pointer_type("void*"), 3)
        init = _init_list(_ident("malloc"), _ident("free"), _ident("realloc"))
        result = gen._emit_static_init("funcs", rtype, init, "static")
        assert result is True
        instr = gen.instructions[0]
        assert instr.op == "gdef_ptr_array"
        entries = instr.meta["entries"]
        assert entries == [("symbol", "malloc"), ("symbol", "free"), ("symbol", "realloc")]

    def test_mixed_pointer_array(self):
        gen = _make_ir_gen()
        rtype = _array_type(_pointer_type("char*"), 3)
        init = _init_list(_str_lit("hello"), _ident("global_str"), _int_lit(0))
        result = gen._emit_static_init("mixed", rtype, init, "")
        assert result is True
        instr = gen.instructions[0]
        assert instr.op == "gdef_ptr_array"
        entries = instr.meta["entries"]
        assert entries == [("string", "hello"), ("symbol", "global_str"), ("null", 0)]

    def test_pointer_array_with_null(self):
        gen = _make_ir_gen()
        rtype = _array_type(_pointer_type("void*"), 2)
        init = _init_list(_ident("func"), _int_lit(0))
        result = gen._emit_static_init("ptrs", rtype, init, "static")
        assert result is True
        instr = gen.instructions[0]
        assert instr.op == "gdef_ptr_array"
        entries = instr.meta["entries"]
        assert entries == [("symbol", "func"), ("null", 0)]


# ---------------------------------------------------------------------------
# Tests: Struct with symbols → gdef_struct
# ---------------------------------------------------------------------------

class TestStructWithSymbolsGdefStruct:
    def test_struct_with_function_pointers(self):
        gen = _make_ir_gen()
        # struct hooks { void* alloc; void* dealloc; void* realloc; }
        rtype = _struct_type("struct hooks", 24, [
            ("alloc", 0, 8, _pointer_type("void*")),
            ("dealloc", 8, 8, _pointer_type("void*")),
            ("realloc", 16, 8, _pointer_type("void*")),
        ])
        init = _init_list(_ident("malloc"), _ident("free"), _ident("realloc"))
        result = gen._emit_static_init("hooks", rtype, init, "static")
        assert result is True
        instr = gen.instructions[0]
        assert instr.op == "gdef_struct"
        assert instr.result == "@hooks"
        assert instr.meta["size"] == 24
        members = instr.meta["members"]
        assert ("symbol", 8, "malloc") in members
        assert ("symbol", 8, "free") in members
        assert ("symbol", 8, "realloc") in members

    def test_struct_mixed_int_and_symbol(self):
        gen = _make_ir_gen()
        # struct { int id; void* func; }
        rtype = _struct_type("struct entry", 16, [
            ("id", 0, 4, _int_type()),
            ("func", 8, 8, _pointer_type("void*")),
        ])
        init = _init_list(_int_lit(42), _ident("handler"))
        result = gen._emit_static_init("entry", rtype, init, "static")
        assert result is True
        instr = gen.instructions[0]
        assert instr.op == "gdef_struct"
        members = instr.meta["members"]
        # Should have int, padding zero, and symbol
        int_members = [m for m in members if m[0] == "int"]
        sym_members = [m for m in members if m[0] == "symbol"]
        assert len(int_members) >= 1
        assert int_members[0][2] == 42
        assert len(sym_members) == 1
        assert sym_members[0][2] == "handler"

    def test_struct_with_string_member(self):
        gen = _make_ir_gen()
        # struct { char* name; int value; }
        rtype = _struct_type("struct kv", 16, [
            ("name", 0, 8, _pointer_type("char*")),
            ("value", 8, 4, _int_type()),
        ])
        init = _init_list(_str_lit("key"), _int_lit(99))
        result = gen._emit_static_init("kv", rtype, init, "static")
        assert result is True
        instr = gen.instructions[0]
        assert instr.op == "gdef_struct"
        members = instr.meta["members"]
        str_members = [m for m in members if m[0] == "string"]
        assert len(str_members) == 1
        assert str_members[0][2] == "key"


# ---------------------------------------------------------------------------
# Tests: Error cases
# ---------------------------------------------------------------------------

class TestErrorCases:
    def test_non_constant_returns_false(self):
        gen = _make_ir_gen()
        rtype = _int_type()
        # Identifier that's not a known symbol in pointer context
        # For scalar context, _const_expr_to_int will fail
        result = gen._emit_static_init("x", rtype, _ident("runtime_var"), "static")
        assert result is False
        assert len(gen.instructions) == 0

    def test_none_rtype_returns_false(self):
        gen = _make_ir_gen()
        result = gen._emit_static_init("x", None, _int_lit(0), "static")
        assert result is False

    def test_storage_class_preserved(self):
        gen = _make_ir_gen()
        rtype = _int_type()
        gen._emit_static_init("x", rtype, _int_lit(1), "extern")
        assert gen.instructions[0].label == "extern"


# ---------------------------------------------------------------------------
# Tests: Nested structures → gdef_blob
# ---------------------------------------------------------------------------

class TestNestedStructBlob:
    def test_array_of_structs(self):
        gen = _make_ir_gen()
        elem_type = _struct_type("struct Point", 8, [
            ("x", 0, 4, _int_type()),
            ("y", 4, 4, _int_type()),
        ])
        rtype = _array_type(elem_type, 2)
        init = _init_list(
            _init_list(_int_lit(1), _int_lit(2)),
            _init_list(_int_lit(3), _int_lit(4)),
        )
        result = gen._emit_static_init("points", rtype, init, "static")
        assert result is True
        instr = gen.instructions[0]
        assert instr.op == "gdef_blob"
        blob_bytes = _blob_bytes(instr.operand2)
        assert len(blob_bytes) == 16
        assert struct.unpack_from("<I", blob_bytes, 0)[0] == 1
        assert struct.unpack_from("<I", blob_bytes, 4)[0] == 2
        assert struct.unpack_from("<I", blob_bytes, 8)[0] == 3
        assert struct.unpack_from("<I", blob_bytes, 12)[0] == 4

    def test_struct_with_array_member(self):
        gen = _make_ir_gen()
        # struct { int data[3]; }
        arr_member = _array_type(_int_type(), 3)
        rtype = _struct_type("struct Buf", 12, [
            ("data", 0, 12, arr_member),
        ])
        init = _init_list(_init_list(_int_lit(10), _int_lit(20), _int_lit(30)))
        result = gen._emit_static_init("buf", rtype, init, "static")
        assert result is True
        instr = gen.instructions[0]
        assert instr.op == "gdef_blob"
        blob_bytes = _blob_bytes(instr.operand2)
        assert len(blob_bytes) == 12
        assert struct.unpack_from("<I", blob_bytes, 0)[0] == 10
        assert struct.unpack_from("<I", blob_bytes, 4)[0] == 20
        assert struct.unpack_from("<I", blob_bytes, 8)[0] == 30
