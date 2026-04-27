"""Unit tests for pycc.target.TargetInfo."""

import pytest
from pycc.target import TargetInfo
from pycc.types import (
    CType, TypeKind, IntegerType, FloatType, PointerType,
    ArrayType, StructType, EnumType, ctype_to_ir_type,
)


@pytest.fixture
def ti():
    return TargetInfo.lp64()


# -- LP64 scalar sizeof/alignof -------------------------------------------

_LP64_SCALARS = {
    "char": 1, "signed char": 1, "unsigned char": 1,
    "short": 2, "short int": 2, "signed short": 2,
    "signed short int": 2, "unsigned short": 2, "unsigned short int": 2,
    "int": 4, "signed int": 4, "unsigned int": 4, "signed": 4,
    "long": 8, "long int": 8, "signed long": 8,
    "signed long int": 8, "unsigned long": 8, "unsigned long int": 8,
    "float": 4, "double": 8, "long double": 16,
}


@pytest.mark.parametrize("name,expected", list(_LP64_SCALARS.items()))
def test_sizeof_scalars(ti, name, expected):
    assert ti.sizeof(name) == expected


@pytest.mark.parametrize("name,expected", list(_LP64_SCALARS.items()))
def test_alignof_scalars(ti, name, expected):
    assert ti.alignof(name) == expected


# -- Pointer types ---------------------------------------------------------

@pytest.mark.parametrize("name", [
    "int *", "char *", "void *", "unsigned long *",
    "struct foo *", "int **",
])
def test_sizeof_pointer_types(ti, name):
    assert ti.sizeof(name) == 8


@pytest.mark.parametrize("name", ["int *", "void *"])
def test_alignof_pointer_types(ti, name):
    assert ti.alignof(name) == 8


# -- Enum types ------------------------------------------------------------

@pytest.mark.parametrize("name", ["enum color", "enum foo"])
def test_sizeof_enum(ti, name):
    assert ti.sizeof(name) == 4


@pytest.mark.parametrize("name", ["enum color", "enum foo"])
def test_alignof_enum(ti, name):
    assert ti.alignof(name) == 4


# -- Unknown type fallback -------------------------------------------------

def test_sizeof_unknown_falls_back_to_pointer_size(ti):
    assert ti.sizeof("some_unknown_type") == 8


def test_alignof_unknown_falls_back_to_pointer_size(ti):
    assert ti.alignof("some_unknown_type") == 8


# -- Void ------------------------------------------------------------------

def test_sizeof_void(ti):
    assert ti.sizeof("void") == 0


# -- __builtin_va_list -----------------------------------------------------

def test_sizeof_builtin_va_list(ti):
    assert ti.sizeof("__builtin_va_list") == 24


# -- Whitespace normalization ----------------------------------------------

def test_sizeof_normalizes_whitespace(ti):
    assert ti.sizeof("  long   int  ") == 8
    assert ti.sizeof("unsigned  short  int") == 2


# -- pointer_size property -------------------------------------------------

def test_pointer_size(ti):
    assert ti.pointer_size == 8


# -- CType interface -------------------------------------------------------

def test_sizeof_ctype_char(ti):
    ct = IntegerType(kind=TypeKind.CHAR)
    assert ti.sizeof_ctype(ct) == 1


def test_sizeof_ctype_int(ti):
    ct = IntegerType(kind=TypeKind.INT)
    assert ti.sizeof_ctype(ct) == 4


def test_sizeof_ctype_long(ti):
    ct = IntegerType(kind=TypeKind.LONG)
    assert ti.sizeof_ctype(ct) == 8


def test_sizeof_ctype_unsigned_int(ti):
    ct = IntegerType(kind=TypeKind.INT, is_unsigned=True)
    assert ti.sizeof_ctype(ct) == 4


def test_sizeof_ctype_float(ti):
    ct = FloatType(kind=TypeKind.FLOAT)
    assert ti.sizeof_ctype(ct) == 4


def test_sizeof_ctype_double(ti):
    ct = FloatType(kind=TypeKind.DOUBLE)
    assert ti.sizeof_ctype(ct) == 8


def test_sizeof_ctype_pointer(ti):
    ct = PointerType(kind=TypeKind.POINTER, pointee=IntegerType(kind=TypeKind.INT))
    assert ti.sizeof_ctype(ct) == 8


def test_sizeof_ctype_enum(ti):
    ct = EnumType(kind=TypeKind.ENUM, tag="color")
    assert ti.sizeof_ctype(ct) == 4


def test_sizeof_ctype_void(ti):
    ct = CType(kind=TypeKind.VOID)
    assert ti.sizeof_ctype(ct) == 0


def test_sizeof_ctype_array(ti):
    elem = IntegerType(kind=TypeKind.INT)
    ct = ArrayType(kind=TypeKind.ARRAY, element=elem, size=10)
    assert ti.sizeof_ctype(ct) == 40


def test_alignof_ctype_array(ti):
    elem = IntegerType(kind=TypeKind.INT)
    ct = ArrayType(kind=TypeKind.ARRAY, element=elem, size=10)
    assert ti.alignof_ctype(ct) == 4


# -- Struct/union delegation to layouts ------------------------------------

class _FakeLayout:
    def __init__(self, size, align=1):
        self.size = size
        self.align = align


def test_sizeof_ctype_struct_with_layout(ti):
    ct = StructType(kind=TypeKind.STRUCT, tag="point")
    layouts = {"struct point": _FakeLayout(size=8, align=4)}
    assert ti.sizeof_ctype(ct, layouts) == 8


def test_alignof_ctype_struct_with_layout(ti):
    ct = StructType(kind=TypeKind.STRUCT, tag="point")
    layouts = {"struct point": _FakeLayout(size=8, align=4)}
    assert ti.alignof_ctype(ct, layouts) == 4


def test_sizeof_ctype_struct_no_layout(ti):
    ct = StructType(kind=TypeKind.STRUCT, tag="unknown")
    assert ti.sizeof_ctype(ct) == 0


def test_sizeof_ctype_union_with_layout(ti):
    ct = StructType(kind=TypeKind.UNION, tag="data")
    layouts = {"union data": _FakeLayout(size=16, align=8)}
    assert ti.sizeof_ctype(ct, layouts) == 16


# -- CType interface consistency with string interface ---------------------

_SCALAR_CTYPES = [
    IntegerType(kind=TypeKind.CHAR),
    IntegerType(kind=TypeKind.CHAR, is_unsigned=True),
    IntegerType(kind=TypeKind.SHORT),
    IntegerType(kind=TypeKind.SHORT, is_unsigned=True),
    IntegerType(kind=TypeKind.INT),
    IntegerType(kind=TypeKind.INT, is_unsigned=True),
    IntegerType(kind=TypeKind.LONG),
    IntegerType(kind=TypeKind.LONG, is_unsigned=True),
    FloatType(kind=TypeKind.FLOAT),
    FloatType(kind=TypeKind.DOUBLE),
    PointerType(kind=TypeKind.POINTER),
    EnumType(kind=TypeKind.ENUM, tag="x"),
]


@pytest.mark.parametrize("ct", _SCALAR_CTYPES)
def test_ctype_sizeof_matches_string_sizeof(ti, ct):
    ir_name = ctype_to_ir_type(ct)
    assert ti.sizeof_ctype(ct) == ti.sizeof(ir_name)
