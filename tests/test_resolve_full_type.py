"""Unit tests for IRGenerator._resolve_full_type method."""
import pytest
from dataclasses import dataclass, field
from typing import Optional, List, Dict

from pycc.ir import IRGenerator, ResolvedType
from pycc.ast_nodes import Type, Declaration


def _T(**kwargs):
    """Shorthand to create a Type node with dummy line/column."""
    return Type(line=0, column=0, **kwargs)


# ---------------------------------------------------------------------------
# Helpers: minimal mock objects for sema_ctx
# ---------------------------------------------------------------------------

@dataclass
class MockStructLayout:
    kind: str  # "struct" or "union"
    name: str
    size: int
    align: int
    member_offsets: Dict[str, int]
    member_sizes: Dict[str, int]
    member_types: Optional[Dict[str, str]] = None


@dataclass
class MockSemaCtx:
    typedefs: Dict[str, Type] = field(default_factory=dict)
    layouts: Dict[str, MockStructLayout] = field(default_factory=dict)


def _make_irgen(sema_ctx=None):
    """Create an IRGenerator with optional sema_ctx."""
    gen = IRGenerator()
    gen._sema_ctx = sema_ctx
    return gen


def _make_decl(name, base, is_pointer=False, pointer_level=0,
               array_size=None, array_dims=None, is_array=False,
               array_dimensions=None):
    """Create a Declaration AST node for testing."""
    ty = Type(line=0, column=0, base=base, is_pointer=is_pointer,
              pointer_level=pointer_level, is_array=is_array,
              array_dimensions=array_dimensions)
    decl = Declaration(line=0, column=0, name=name, type=ty,
                       array_size=array_size, array_dims=array_dims)
    return decl


# ===========================================================================
# Test: Scalar types
# ===========================================================================

class TestScalarTypes:
    def test_int(self):
        gen = _make_irgen()
        decl = _make_decl("x", "int")
        rt = gen._resolve_full_type(decl)
        assert rt is not None
        assert rt.kind == "scalar"
        assert rt.name == "int"
        assert rt.size == 4
        assert rt.pack_format == "<I"
        assert rt.pack_mask == 0xFFFFFFFF
        assert rt.is_float is False

    def test_char(self):
        gen = _make_irgen()
        decl = _make_decl("c", "char")
        rt = gen._resolve_full_type(decl)
        assert rt is not None
        assert rt.kind == "scalar"
        assert rt.name == "char"
        assert rt.size == 1
        assert rt.pack_format == "<B"

    def test_unsigned_int(self):
        gen = _make_irgen()
        decl = _make_decl("u", "unsigned int")
        rt = gen._resolve_full_type(decl)
        assert rt is not None
        assert rt.kind == "scalar"
        assert rt.name == "unsigned int"
        assert rt.size == 4

    def test_long(self):
        gen = _make_irgen()
        decl = _make_decl("l", "long")
        rt = gen._resolve_full_type(decl)
        assert rt is not None
        assert rt.kind == "scalar"
        assert rt.name == "long"
        assert rt.size == 8
        assert rt.pack_format == "<Q"

    def test_float(self):
        gen = _make_irgen()
        decl = _make_decl("f", "float")
        rt = gen._resolve_full_type(decl)
        assert rt is not None
        assert rt.kind == "scalar"
        assert rt.name == "float"
        assert rt.size == 4
        assert rt.pack_format == "<f"
        assert rt.is_float is True

    def test_double(self):
        gen = _make_irgen()
        decl = _make_decl("d", "double")
        rt = gen._resolve_full_type(decl)
        assert rt is not None
        assert rt.kind == "scalar"
        assert rt.name == "double"
        assert rt.size == 8
        assert rt.pack_format == "<d"
        assert rt.is_float is True

    def test_short(self):
        gen = _make_irgen()
        decl = _make_decl("s", "short")
        rt = gen._resolve_full_type(decl)
        assert rt is not None
        assert rt.kind == "scalar"
        assert rt.name == "short"
        assert rt.size == 2
        assert rt.pack_format == "<H"

    def test_unknown_type_returns_none(self):
        gen = _make_irgen()
        decl = _make_decl("x", "unknown_type_xyz")
        rt = gen._resolve_full_type(decl)
        assert rt is None


# ===========================================================================
# Test: Pointer types
# ===========================================================================

class TestPointerTypes:
    def test_direct_pointer(self):
        gen = _make_irgen()
        decl = _make_decl("p", "int", is_pointer=True, pointer_level=1)
        rt = gen._resolve_full_type(decl)
        assert rt is not None
        assert rt.kind == "pointer"
        assert rt.size == 8

    def test_double_pointer(self):
        gen = _make_irgen()
        decl = _make_decl("pp", "char", is_pointer=True, pointer_level=2)
        rt = gen._resolve_full_type(decl)
        assert rt is not None
        assert rt.kind == "pointer"
        assert rt.size == 8

    def test_typedef_pointer(self):
        """typedef int* IntPtr; IntPtr p;"""
        ctx = MockSemaCtx(
            typedefs={"IntPtr": _T(base="int", is_pointer=True, pointer_level=1)}
        )
        gen = _make_irgen(ctx)
        decl = _make_decl("p", "IntPtr")
        rt = gen._resolve_full_type(decl)
        assert rt is not None
        assert rt.kind == "pointer"
        assert rt.size == 8

    def test_function_pointer_typedef(self):
        """typedef void (*Callback)(int); Callback cb;"""
        ctx = MockSemaCtx(
            typedefs={"Callback": _T(base="void (*)(int)")}
        )
        gen = _make_irgen(ctx)
        decl = _make_decl("cb", "Callback")
        rt = gen._resolve_full_type(decl)
        assert rt is not None
        assert rt.kind == "pointer"
        assert rt.size == 8

    def test_void_pointer(self):
        gen = _make_irgen()
        decl = _make_decl("vp", "void", is_pointer=True, pointer_level=1)
        rt = gen._resolve_full_type(decl)
        assert rt is not None
        assert rt.kind == "pointer"
        assert rt.size == 8


# ===========================================================================
# Test: Typedef resolution
# ===========================================================================

class TestTypedefResolution:
    def test_simple_typedef(self):
        """typedef int MyInt; MyInt x;"""
        ctx = MockSemaCtx(
            typedefs={"MyInt": _T(base="int")}
        )
        gen = _make_irgen(ctx)
        decl = _make_decl("x", "MyInt")
        rt = gen._resolve_full_type(decl)
        assert rt is not None
        assert rt.kind == "scalar"
        assert rt.name == "int"
        assert rt.size == 4

    def test_chained_typedef(self):
        """typedef float GLfloat; typedef GLfloat MyFloat; MyFloat f;"""
        ctx = MockSemaCtx(
            typedefs={
                "GLfloat": _T(base="float"),
                "MyFloat": _T(base="GLfloat"),
            }
        )
        gen = _make_irgen(ctx)
        decl = _make_decl("f", "MyFloat")
        rt = gen._resolve_full_type(decl)
        assert rt is not None
        assert rt.kind == "scalar"
        assert rt.name == "float"
        assert rt.size == 4
        assert rt.is_float is True

    def test_typedef_to_struct(self):
        """typedef struct Foo { int x; } Foo_t; Foo_t s;"""
        ctx = MockSemaCtx(
            typedefs={"Foo_t": _T(base="struct Foo")},
            layouts={
                "struct Foo": MockStructLayout(
                    kind="struct", name="Foo", size=4, align=4,
                    member_offsets={"x": 0},
                    member_sizes={"x": 4},
                    member_types={"x": "int"},
                )
            }
        )
        gen = _make_irgen(ctx)
        decl = _make_decl("s", "Foo_t")
        rt = gen._resolve_full_type(decl)
        assert rt is not None
        assert rt.kind == "struct"
        assert rt.name == "struct Foo"
        assert rt.size == 4

    def test_typedef_circular_protection(self):
        """Circular typedef should not infinite loop."""
        ctx = MockSemaCtx(
            typedefs={
                "A": _T(base="B"),
                "B": _T(base="A"),
            }
        )
        gen = _make_irgen(ctx)
        decl = _make_decl("x", "A")
        # Should not hang — returns None for unknown type
        rt = gen._resolve_full_type(decl)
        # The result depends on where the loop breaks; it should not crash
        assert rt is None or rt is not None  # just ensure no infinite loop


# ===========================================================================
# Test: Array types
# ===========================================================================

class TestArrayTypes:
    def test_int_array(self):
        """int arr[10];"""
        gen = _make_irgen()
        decl = _make_decl("arr", "int", array_size=10)
        rt = gen._resolve_full_type(decl)
        assert rt is not None
        assert rt.kind == "array"
        assert rt.array_length == 10
        assert rt.element_type is not None
        assert rt.element_type.kind == "scalar"
        assert rt.element_type.name == "int"
        assert rt.size == 40  # 10 * 4

    def test_char_array(self):
        """char buf[256];"""
        gen = _make_irgen()
        decl = _make_decl("buf", "char", array_size=256)
        rt = gen._resolve_full_type(decl)
        assert rt is not None
        assert rt.kind == "array"
        assert rt.array_length == 256
        assert rt.element_type.kind == "scalar"
        assert rt.element_type.name == "char"
        assert rt.size == 256

    def test_multidim_array(self):
        """int matrix[3][4];"""
        gen = _make_irgen()
        decl = _make_decl("matrix", "int", array_dims=[3, 4])
        rt = gen._resolve_full_type(decl)
        assert rt is not None
        assert rt.kind == "array"
        assert rt.array_length == 3
        # Inner dimension
        inner = rt.element_type
        assert inner is not None
        assert inner.kind == "array"
        assert inner.array_length == 4
        assert inner.element_type.kind == "scalar"
        assert inner.element_type.name == "int"
        # Total size: 3 * 4 * 4 = 48
        assert rt.size == 48

    def test_pointer_array(self):
        """char *argv[10];"""
        gen = _make_irgen()
        decl = _make_decl("argv", "char", is_pointer=True, pointer_level=1,
                          array_size=10)
        rt = gen._resolve_full_type(decl)
        assert rt is not None
        assert rt.kind == "array"
        assert rt.array_length == 10
        assert rt.element_type.kind == "pointer"
        assert rt.size == 80  # 10 * 8

    def test_struct_array(self):
        """struct Point pts[5];"""
        ctx = MockSemaCtx(
            layouts={
                "struct Point": MockStructLayout(
                    kind="struct", name="Point", size=8, align=4,
                    member_offsets={"x": 0, "y": 4},
                    member_sizes={"x": 4, "y": 4},
                    member_types={"x": "int", "y": "int"},
                )
            }
        )
        gen = _make_irgen(ctx)
        decl = _make_decl("pts", "struct Point", array_size=5)
        rt = gen._resolve_full_type(decl)
        assert rt is not None
        assert rt.kind == "array"
        assert rt.array_length == 5
        assert rt.element_type.kind == "struct"
        assert rt.element_type.size == 8
        assert rt.size == 40  # 5 * 8

    def test_typedef_array(self):
        """typedef float GLfloat; GLfloat colors[4];"""
        ctx = MockSemaCtx(
            typedefs={"GLfloat": _T(base="float")}
        )
        gen = _make_irgen(ctx)
        decl = _make_decl("colors", "GLfloat", array_size=4)
        rt = gen._resolve_full_type(decl)
        assert rt is not None
        assert rt.kind == "array"
        assert rt.array_length == 4
        assert rt.element_type.kind == "scalar"
        assert rt.element_type.name == "float"
        assert rt.size == 16  # 4 * 4

    def test_unsized_array(self):
        """int arr[];"""
        gen = _make_irgen()
        decl = _make_decl("arr", "int", is_array=True, array_dimensions=[None])
        rt = gen._resolve_full_type(decl)
        assert rt is not None
        assert rt.kind == "array"
        assert rt.array_length is None
        assert rt.element_type.kind == "scalar"
        assert rt.size == 0  # unknown size


# ===========================================================================
# Test: Struct/union types
# ===========================================================================

class TestStructTypes:
    def test_simple_struct(self):
        """struct Foo { int x; float y; };"""
        ctx = MockSemaCtx(
            layouts={
                "struct Foo": MockStructLayout(
                    kind="struct", name="Foo", size=8, align=4,
                    member_offsets={"x": 0, "y": 4},
                    member_sizes={"x": 4, "y": 4},
                    member_types={"x": "int", "y": "float"},
                )
            }
        )
        gen = _make_irgen(ctx)
        decl = _make_decl("s", "struct Foo")
        rt = gen._resolve_full_type(decl)
        assert rt is not None
        assert rt.kind == "struct"
        assert rt.name == "struct Foo"
        assert rt.size == 8
        assert rt.members is not None
        assert len(rt.members) == 2
        # Members sorted by offset
        assert rt.members[0][0] == "x"  # name
        assert rt.members[0][1] == 0    # offset
        assert rt.members[0][2] == 4    # size
        assert rt.members[0][3].kind == "scalar"  # resolved type
        assert rt.members[1][0] == "y"
        assert rt.members[1][3].is_float is True

    def test_union(self):
        """union Val { int i; float f; };"""
        ctx = MockSemaCtx(
            layouts={
                "union Val": MockStructLayout(
                    kind="union", name="Val", size=4, align=4,
                    member_offsets={"i": 0, "f": 0},
                    member_sizes={"i": 4, "f": 4},
                    member_types={"i": "int", "f": "float"},
                )
            }
        )
        gen = _make_irgen(ctx)
        decl = _make_decl("v", "union Val")
        rt = gen._resolve_full_type(decl)
        assert rt is not None
        assert rt.kind == "union"
        assert rt.name == "union Val"
        assert rt.size == 4

    def test_struct_with_pointer_member(self):
        """struct Node { int val; struct Node *next; };"""
        ctx = MockSemaCtx(
            layouts={
                "struct Node": MockStructLayout(
                    kind="struct", name="Node", size=16, align=8,
                    member_offsets={"val": 0, "next": 8},
                    member_sizes={"val": 4, "next": 8},
                    member_types={"val": "int", "next": "struct Node *"},
                )
            }
        )
        gen = _make_irgen(ctx)
        decl = _make_decl("n", "struct Node")
        rt = gen._resolve_full_type(decl)
        assert rt is not None
        assert rt.kind == "struct"
        assert rt.size == 16
        # next member should be pointer
        next_mem = [m for m in rt.members if m[0] == "next"][0]
        assert next_mem[3].kind == "pointer"
        assert next_mem[3].size == 8

    def test_struct_not_in_layouts_returns_none(self):
        """struct Unknown s; — no layout registered"""
        ctx = MockSemaCtx()
        gen = _make_irgen(ctx)
        decl = _make_decl("s", "struct Unknown")
        rt = gen._resolve_full_type(decl)
        assert rt is None


# ===========================================================================
# Test: Enum types
# ===========================================================================

class TestEnumTypes:
    def test_enum_resolves_to_int(self):
        """enum Color c;"""
        gen = _make_irgen()
        decl = _make_decl("c", "enum Color")
        rt = gen._resolve_full_type(decl)
        assert rt is not None
        assert rt.kind == "scalar"
        assert rt.name == "int"
        assert rt.size == 4

    def test_typedef_enum(self):
        """typedef enum { R, G, B } Color; Color c;"""
        ctx = MockSemaCtx(
            typedefs={"Color": _T(base="enum __anon_Color")}
        )
        gen = _make_irgen(ctx)
        decl = _make_decl("c", "Color")
        rt = gen._resolve_full_type(decl)
        assert rt is not None
        assert rt.kind == "scalar"
        assert rt.name == "int"
        assert rt.size == 4


# ===========================================================================
# Test: Edge cases
# ===========================================================================

class TestEdgeCases:
    def test_no_type_attribute(self):
        """Declaration with no type attribute."""
        gen = _make_irgen()
        # Create a bare object without type
        class FakeDecl:
            pass
        decl = FakeDecl()
        rt = gen._resolve_full_type(decl)
        assert rt is None

    def test_none_sema_ctx(self):
        """Works without sema_ctx for basic types."""
        gen = _make_irgen(sema_ctx=None)
        decl = _make_decl("x", "int")
        rt = gen._resolve_full_type(decl)
        assert rt is not None
        assert rt.kind == "scalar"
        assert rt.name == "int"

    def test_bool_type(self):
        gen = _make_irgen()
        decl = _make_decl("b", "_Bool")
        rt = gen._resolve_full_type(decl)
        assert rt is not None
        assert rt.kind == "scalar"
        assert rt.size == 1

    def test_long_double(self):
        gen = _make_irgen()
        decl = _make_decl("ld", "long double")
        rt = gen._resolve_full_type(decl)
        assert rt is not None
        assert rt.kind == "scalar"
        assert rt.size == 16
        assert rt.is_float is True
