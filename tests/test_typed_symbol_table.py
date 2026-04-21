"""Unit tests for TypedSymbolTable."""
import pytest
from unittest.mock import MagicMock

from pycc.types import (
    TypedSymbolTable,
    CType, IntegerType, FloatType, PointerType, ArrayType,
    StructType, EnumType, FunctionTypeCType,
    TypeKind, Qualifiers,
)
from pycc.ast_nodes import Type


def _ty(base, **kwargs):
    """Shorthand to create an ast_nodes.Type with dummy line/column."""
    return Type(line=0, column=0, base=base, **kwargs)


def _make_sema_ctx(typedefs=None, layouts=None):
    """Create a minimal mock SemanticContext with typedefs."""
    ctx = MagicMock()
    ctx.typedefs = typedefs or {}
    ctx.layouts = layouts or {}
    return ctx


class TestBasicOperations:
    """Test push_scope, pop_scope, insert, lookup."""

    def test_insert_and_lookup_global(self):
        st = TypedSymbolTable()
        ct = IntegerType(kind=TypeKind.INT)
        st.insert("@x", ct)
        assert st.lookup("@x") is ct

    def test_lookup_missing_returns_none(self):
        st = TypedSymbolTable()
        assert st.lookup("@missing") is None

    def test_insert_into_scope(self):
        st = TypedSymbolTable()
        st.push_scope()
        ct = IntegerType(kind=TypeKind.LONG)
        st.insert("@y", ct)
        assert st.lookup("@y") is ct
        st.pop_scope()
        assert st.lookup("@y") is None

    def test_scope_shadows_global(self):
        st = TypedSymbolTable()
        global_ct = IntegerType(kind=TypeKind.INT)
        local_ct = FloatType(kind=TypeKind.FLOAT)
        st.insert("@x", global_ct)
        st.push_scope()
        st.insert("@x", local_ct)
        assert st.lookup("@x") is local_ct
        st.pop_scope()
        assert st.lookup("@x") is global_ct

    def test_global_fallback_from_scope(self):
        st = TypedSymbolTable()
        ct = IntegerType(kind=TypeKind.INT)
        st.insert("@g", ct)
        st.push_scope()
        assert st.lookup("@g") is ct
        st.pop_scope()

    def test_nested_scopes(self):
        st = TypedSymbolTable()
        ct1 = IntegerType(kind=TypeKind.INT)
        ct2 = FloatType(kind=TypeKind.FLOAT)
        st.push_scope()
        st.insert("@x", ct1)
        st.push_scope()
        st.insert("@x", ct2)
        assert st.lookup("@x") is ct2
        st.pop_scope()
        assert st.lookup("@x") is ct1
        st.pop_scope()


class TestTypedefResolution:
    """Test _resolve_typedef with SemanticContext.typedefs."""

    def test_simple_typedef(self):
        """GLfloat -> float"""
        sema = _make_sema_ctx(typedefs={"GLfloat": _ty("float")})
        st = TypedSymbolTable(sema_ctx=sema)
        resolved = st._resolve_typedef_name("GLfloat", set())
        assert resolved is not None
        assert resolved.kind == TypeKind.FLOAT

    def test_typedef_to_struct(self):
        """hooks_t -> struct internal_hooks"""
        sema = _make_sema_ctx(typedefs={"hooks_t": _ty("struct internal_hooks")})
        st = TypedSymbolTable(sema_ctx=sema)
        resolved = st._resolve_typedef_name("hooks_t", set())
        assert resolved is not None
        assert resolved.kind == TypeKind.STRUCT
        assert isinstance(resolved, StructType)
        assert resolved.tag == "internal_hooks"

    def test_chained_typedef(self):
        """MyInt -> GLint -> int"""
        sema = _make_sema_ctx(typedefs={
            "MyInt": _ty("GLint"),
            "GLint": _ty("int"),
        })
        st = TypedSymbolTable(sema_ctx=sema)
        resolved = st._resolve_typedef_name("MyInt", set())
        assert resolved is not None
        assert resolved.kind == TypeKind.INT

    def test_circular_typedef_stops(self):
        """A -> B -> A should not infinite loop."""
        sema = _make_sema_ctx(typedefs={
            "A": _ty("B"),
            "B": _ty("A"),
        })
        st = TypedSymbolTable(sema_ctx=sema)
        result = st._resolve_typedef_name("A", set())
        # Should not raise - cycle detection prevents infinite loop
        assert result is not None

    def test_pointer_to_typedef_struct(self):
        """PointerType(pointee=StructType(tag='hooks_t')) should resolve pointee."""
        sema = _make_sema_ctx(typedefs={"hooks_t": _ty("struct internal_hooks")})
        st = TypedSymbolTable(sema_ctx=sema)
        ct = PointerType(
            kind=TypeKind.POINTER,
            pointee=StructType(kind=TypeKind.STRUCT, tag="hooks_t"),
        )
        resolved = st._resolve_typedef(ct)
        assert isinstance(resolved, PointerType)
        assert isinstance(resolved.pointee, StructType)
        assert resolved.pointee.tag == "internal_hooks"

    def test_array_of_typedef(self):
        """ArrayType(element=StructType(tag='GLfloat')) should resolve element."""
        sema = _make_sema_ctx(typedefs={"GLfloat": _ty("float")})
        st = TypedSymbolTable(sema_ctx=sema)
        ct = ArrayType(
            kind=TypeKind.ARRAY,
            element=StructType(kind=TypeKind.STRUCT, tag="GLfloat"),
            size=10,
        )
        resolved = st._resolve_typedef(ct)
        assert isinstance(resolved, ArrayType)
        assert resolved.element.kind == TypeKind.FLOAT
        assert resolved.size == 10

    def test_no_sema_ctx_passthrough(self):
        """Without sema_ctx, _resolve_typedef returns ctype unchanged."""
        st = TypedSymbolTable(sema_ctx=None)
        ct = StructType(kind=TypeKind.STRUCT, tag="hooks_t")
        assert st._resolve_typedef(ct) is ct

    def test_non_typedef_struct_unchanged(self):
        """StructType with a real struct tag (not a typedef) stays unchanged."""
        sema = _make_sema_ctx(typedefs={})
        st = TypedSymbolTable(sema_ctx=sema)
        ct = StructType(kind=TypeKind.STRUCT, tag="cJSON")
        resolved = st._resolve_typedef(ct)
        assert resolved is ct

    def test_insert_resolves_typedef(self):
        """insert() should resolve typedefs before storing."""
        sema = _make_sema_ctx(typedefs={"GLfloat": _ty("float")})
        st = TypedSymbolTable(sema_ctx=sema)
        ct = StructType(kind=TypeKind.STRUCT, tag="GLfloat")
        st.insert("@x", ct)
        result = st.lookup("@x")
        assert result.kind == TypeKind.FLOAT


class TestQualifierPreservation:
    """Test that qualifiers are preserved during typedef resolution."""

    def test_const_preserved_on_typedef(self):
        """const GLfloat -> const float"""
        sema = _make_sema_ctx(typedefs={"GLfloat": _ty("float")})
        st = TypedSymbolTable(sema_ctx=sema)
        ct = StructType(
            kind=TypeKind.STRUCT,
            quals=Qualifiers(const=True),
            tag="GLfloat",
        )
        resolved = st._resolve_typedef(ct)
        assert resolved.kind == TypeKind.FLOAT
        assert resolved.quals.const is True

    def test_volatile_preserved_on_typedef(self):
        sema = _make_sema_ctx(typedefs={"MyInt": _ty("int")})
        st = TypedSymbolTable(sema_ctx=sema)
        ct = StructType(
            kind=TypeKind.STRUCT,
            quals=Qualifiers(volatile=True),
            tag="MyInt",
        )
        resolved = st._resolve_typedef(ct)
        assert resolved.kind == TypeKind.INT
        assert resolved.quals.volatile is True

    def test_pointer_qualifiers_preserved(self):
        """const pointer to typedef should preserve pointer quals."""
        sema = _make_sema_ctx(typedefs={"hooks_t": _ty("struct internal_hooks")})
        st = TypedSymbolTable(sema_ctx=sema)
        ct = PointerType(
            kind=TypeKind.POINTER,
            quals=Qualifiers(const=True),
            pointee=StructType(kind=TypeKind.STRUCT, tag="hooks_t"),
        )
        resolved = st._resolve_typedef(ct)
        assert isinstance(resolved, PointerType)
        assert resolved.quals.const is True
        assert isinstance(resolved.pointee, StructType)
        assert resolved.pointee.tag == "internal_hooks"

    def test_typedef_to_pointer_with_const(self):
        """typedef int *IntPtr; const IntPtr -> const pointer to int"""
        sema = _make_sema_ctx(typedefs={
            "IntPtr": _ty("int", is_pointer=True, pointer_level=1),
        })
        st = TypedSymbolTable(sema_ctx=sema)
        ct = StructType(
            kind=TypeKind.STRUCT,
            quals=Qualifiers(const=True),
            tag="IntPtr",
        )
        resolved = st._resolve_typedef(ct)
        assert isinstance(resolved, PointerType)
        assert resolved.quals.const is True
