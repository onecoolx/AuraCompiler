"""Unit tests for is_array being set on struct member array declarations.

Validates: Requirements 2.3

Tests that _parse_struct_or_union_specifier correctly sets Type.is_array=True
for struct/union member declarations with array dimensions, while preserving
backward-compatible array_size/array_dims fields.
"""

from pycc.ast_nodes import Declaration, StructDecl, UnionDecl, Type
from pycc.lexer import Lexer
from pycc.parser import Parser


def _parse_struct(code: str) -> StructDecl:
    """Parse code and return the first StructDecl."""
    tokens = Lexer(code).tokenize()
    ast = Parser(tokens).parse()
    for decl in ast.declarations:
        if isinstance(decl, StructDecl):
            return decl
    raise AssertionError("No StructDecl found in parsed AST")


def _parse_union(code: str) -> UnionDecl:
    """Parse code and return the first UnionDecl."""
    tokens = Lexer(code).tokenize()
    ast = Parser(tokens).parse()
    for decl in ast.declarations:
        if isinstance(decl, UnionDecl):
            return decl
    raise AssertionError("No UnionDecl found in parsed AST")


class TestStructMemberArrayIsArray:
    """Struct member array declarations should have type.is_array=True."""

    def test_simple_char_array_member(self):
        """char name[32]; -> type.is_array=True"""
        sd = _parse_struct("struct Foo { char name[32]; };")
        member = sd.members[0]
        assert member.name == "name"
        assert member.type.is_array is True
        assert member.type.array_dimensions == [32]
        assert member.type.array_element_type is not None
        assert member.type.array_element_type.base == "char"
        assert member.type.array_element_type.is_array is False

    def test_int_array_member(self):
        """int data[8]; -> type.is_array=True"""
        sd = _parse_struct("struct Bar { int data[8]; };")
        member = sd.members[0]
        assert member.name == "data"
        assert member.type.is_array is True
        assert member.type.array_dimensions == [8]
        assert member.type.array_element_type.base == "int"

    def test_multidim_array_member(self):
        """int matrix[3][4]; -> nested array types"""
        sd = _parse_struct("struct M { int matrix[3][4]; };")
        member = sd.members[0]
        assert member.name == "matrix"
        assert member.type.is_array is True
        assert member.type.array_dimensions == [3, 4]
        inner = member.type.array_element_type
        assert inner.is_array is True
        assert inner.array_dimensions == [4]
        leaf = inner.array_element_type
        assert leaf.base == "int"
        assert leaf.is_array is False

    def test_non_array_member_not_marked(self):
        """int x; -> type.is_array=False"""
        sd = _parse_struct("struct S { int x; };")
        member = sd.members[0]
        assert member.name == "x"
        assert member.type.is_array is False

    def test_pointer_member_not_marked(self):
        """int *p; -> type.is_array=False"""
        sd = _parse_struct("struct S { int *p; };")
        member = sd.members[0]
        assert member.name == "p"
        assert member.type.is_array is False

    def test_backward_compat_array_size_preserved(self):
        """array_size and array_dims fields still set for backward compat"""
        sd = _parse_struct("struct S { long data[8]; };")
        member = sd.members[0]
        assert member.array_size == 8
        assert member.array_dims == [8]
        # And is_array is also set
        assert member.type.is_array is True

    def test_multi_declarator_array_member(self):
        """int a[2], b[3]; -> both have is_array=True"""
        sd = _parse_struct("struct S { int a[2], b[3]; };")
        assert len(sd.members) == 2
        assert sd.members[0].name == "a"
        assert sd.members[0].type.is_array is True
        assert sd.members[0].type.array_dimensions == [2]
        assert sd.members[1].name == "b"
        assert sd.members[1].type.is_array is True
        assert sd.members[1].type.array_dimensions == [3]

    def test_mixed_array_and_scalar_members(self):
        """struct with both array and non-array members"""
        sd = _parse_struct("struct S { int x; char buf[64]; float *p; };")
        assert sd.members[0].name == "x"
        assert sd.members[0].type.is_array is False
        assert sd.members[1].name == "buf"
        assert sd.members[1].type.is_array is True
        assert sd.members[1].type.array_dimensions == [64]
        assert sd.members[2].name == "p"
        assert sd.members[2].type.is_array is False

    def test_union_member_array(self):
        """Union members with arrays also get is_array=True"""
        ud = _parse_union("union U { int arr[4]; char bytes[16]; };")
        assert ud.members[0].name == "arr"
        assert ud.members[0].type.is_array is True
        assert ud.members[0].type.array_dimensions == [4]
        assert ud.members[1].name == "bytes"
        assert ud.members[1].type.is_array is True
        assert ud.members[1].type.array_dimensions == [16]
