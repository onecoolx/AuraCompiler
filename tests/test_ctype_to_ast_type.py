"""Unit tests for ctype_to_ast_type bridge function."""

import pytest

from pycc.types import (
    ctype_to_ast_type,
    CType,
    IntegerType,
    FloatType,
    PointerType,
    ArrayType,
    StructType,
    EnumType,
    TypeKind,
    Qualifiers,
)


class TestIntegerType:
    def test_int(self):
        ct = IntegerType(kind=TypeKind.INT, is_unsigned=False)
        ast_t = ctype_to_ast_type(ct)
        assert ast_t.base == 'int'
        assert not ast_t.is_unsigned
        assert not ast_t.is_pointer

    def test_unsigned_int(self):
        ct = IntegerType(kind=TypeKind.INT, is_unsigned=True)
        ast_t = ctype_to_ast_type(ct)
        assert ast_t.base == 'int'
        assert ast_t.is_unsigned

    def test_char(self):
        ct = IntegerType(kind=TypeKind.CHAR, is_unsigned=False)
        ast_t = ctype_to_ast_type(ct)
        assert ast_t.base == 'char'
        assert not ast_t.is_unsigned

    def test_unsigned_char(self):
        ct = IntegerType(kind=TypeKind.CHAR, is_unsigned=True)
        ast_t = ctype_to_ast_type(ct)
        assert ast_t.base == 'char'
        assert ast_t.is_unsigned

    def test_short(self):
        ct = IntegerType(kind=TypeKind.SHORT, is_unsigned=False)
        ast_t = ctype_to_ast_type(ct)
        assert ast_t.base == 'short'

    def test_long(self):
        ct = IntegerType(kind=TypeKind.LONG, is_unsigned=False)
        ast_t = ctype_to_ast_type(ct)
        assert ast_t.base == 'long'

    def test_unsigned_long(self):
        ct = IntegerType(kind=TypeKind.LONG, is_unsigned=True)
        ast_t = ctype_to_ast_type(ct)
        assert ast_t.base == 'long'
        assert ast_t.is_unsigned

    def test_const_int(self):
        ct = IntegerType(kind=TypeKind.INT, quals=Qualifiers(const=True))
        ast_t = ctype_to_ast_type(ct)
        assert ast_t.base == 'int'
        assert ast_t.is_const


class TestFloatType:
    def test_float(self):
        ct = FloatType(kind=TypeKind.FLOAT)
        ast_t = ctype_to_ast_type(ct)
        assert ast_t.base == 'float'

    def test_double(self):
        ct = FloatType(kind=TypeKind.DOUBLE)
        ast_t = ctype_to_ast_type(ct)
        assert ast_t.base == 'double'

    def test_const_double(self):
        ct = FloatType(kind=TypeKind.DOUBLE, quals=Qualifiers(const=True))
        ast_t = ctype_to_ast_type(ct)
        assert ast_t.base == 'double'
        assert ast_t.is_const


class TestPointerType:
    def test_pointer_to_int(self):
        ct = PointerType(kind=TypeKind.POINTER, pointee=IntegerType(kind=TypeKind.INT))
        ast_t = ctype_to_ast_type(ct)
        assert ast_t.is_pointer
        assert ast_t.pointer_level == 1
        assert ast_t.base == 'int'

    def test_pointer_to_char(self):
        ct = PointerType(kind=TypeKind.POINTER, pointee=IntegerType(kind=TypeKind.CHAR))
        ast_t = ctype_to_ast_type(ct)
        assert ast_t.is_pointer
        assert ast_t.pointer_level == 1
        assert ast_t.base == 'char'

    def test_double_pointer(self):
        inner = PointerType(kind=TypeKind.POINTER, pointee=IntegerType(kind=TypeKind.INT))
        ct = PointerType(kind=TypeKind.POINTER, pointee=inner)
        ast_t = ctype_to_ast_type(ct)
        assert ast_t.pointer_level == 2
        assert ast_t.base == 'int'

    def test_pointer_to_void(self):
        ct = PointerType(kind=TypeKind.POINTER, pointee=CType(kind=TypeKind.VOID))
        ast_t = ctype_to_ast_type(ct)
        assert ast_t.is_pointer
        assert ast_t.pointer_level == 1
        assert ast_t.base == 'void'

    def test_const_pointer(self):
        ct = PointerType(
            kind=TypeKind.POINTER,
            quals=Qualifiers(const=True),
            pointee=IntegerType(kind=TypeKind.INT),
        )
        ast_t = ctype_to_ast_type(ct)
        assert ast_t.is_pointer
        assert 'const' in ast_t.pointer_quals[0]

    def test_pointer_to_struct(self):
        ct = PointerType(
            kind=TypeKind.POINTER,
            pointee=StructType(kind=TypeKind.STRUCT, tag='Node'),
        )
        ast_t = ctype_to_ast_type(ct)
        assert ast_t.is_pointer
        assert ast_t.pointer_level == 1
        assert ast_t.base == 'struct Node'

    def test_null_pointee(self):
        ct = PointerType(kind=TypeKind.POINTER, pointee=None)
        ast_t = ctype_to_ast_type(ct)
        assert ast_t.is_pointer
        assert ast_t.base == 'void'


class TestArrayType:
    def test_int_array(self):
        ct = ArrayType(kind=TypeKind.ARRAY, element=IntegerType(kind=TypeKind.INT), size=10)
        ast_t = ctype_to_ast_type(ct)
        assert ast_t.is_array
        assert ast_t.array_dimensions == [10]
        assert ast_t.base == 'int'

    def test_unsized_array(self):
        ct = ArrayType(kind=TypeKind.ARRAY, element=IntegerType(kind=TypeKind.INT), size=None)
        ast_t = ctype_to_ast_type(ct)
        assert ast_t.is_array
        assert ast_t.array_dimensions == [None]

    def test_char_array(self):
        ct = ArrayType(kind=TypeKind.ARRAY, element=IntegerType(kind=TypeKind.CHAR), size=256)
        ast_t = ctype_to_ast_type(ct)
        assert ast_t.is_array
        assert ast_t.base == 'char'
        assert ast_t.array_dimensions == [256]


class TestStructType:
    def test_struct(self):
        ct = StructType(kind=TypeKind.STRUCT, tag='Point')
        ast_t = ctype_to_ast_type(ct)
        assert ast_t.base == 'struct Point'
        assert not ast_t.is_pointer

    def test_union(self):
        ct = StructType(kind=TypeKind.UNION, tag='Data')
        ast_t = ctype_to_ast_type(ct)
        assert ast_t.base == 'union Data'

    def test_anonymous_struct(self):
        ct = StructType(kind=TypeKind.STRUCT, tag=None)
        ast_t = ctype_to_ast_type(ct)
        assert ast_t.base == 'struct'

    def test_const_struct(self):
        ct = StructType(kind=TypeKind.STRUCT, tag='Foo', quals=Qualifiers(const=True))
        ast_t = ctype_to_ast_type(ct)
        assert ast_t.base == 'struct Foo'
        assert ast_t.is_const


class TestEnumType:
    def test_enum(self):
        ct = EnumType(kind=TypeKind.ENUM, tag='Color')
        ast_t = ctype_to_ast_type(ct)
        assert ast_t.base == 'enum Color'

    def test_anonymous_enum(self):
        ct = EnumType(kind=TypeKind.ENUM, tag=None)
        ast_t = ctype_to_ast_type(ct)
        assert ast_t.base == 'int'

    def test_anonymous_enum_empty_tag(self):
        ct = EnumType(kind=TypeKind.ENUM, tag='')
        ast_t = ctype_to_ast_type(ct)
        assert ast_t.base == 'int'


class TestEdgeCases:
    def test_none_input(self):
        assert ctype_to_ast_type(None) is None

    def test_void_type(self):
        ct = CType(kind=TypeKind.VOID)
        ast_t = ctype_to_ast_type(ct)
        assert ast_t.base == 'void'

    def test_volatile_qualifier(self):
        ct = IntegerType(kind=TypeKind.INT, quals=Qualifiers(volatile=True))
        ast_t = ctype_to_ast_type(ct)
        assert ast_t.is_volatile
