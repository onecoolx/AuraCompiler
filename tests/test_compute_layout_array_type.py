"""Unit tests for _compute_layout storing array info in member_decl_types Type.

Verifies that when a struct member is an array, the Type stored in
layout.member_decl_types has is_array=True, correct array_element_type,
and array_dimensions.
"""

from pycc.lexer import Lexer
from pycc.parser import Parser
from pycc.semantics import SemanticAnalyzer


def _get_layout(code: str, struct_key: str):
    """Parse code and return the StructLayout for the given key."""
    tokens = Lexer(code).tokenize()
    ast = Parser(tokens).parse()
    sa = SemanticAnalyzer()
    ctx = sa.analyze(ast)
    return ctx.layouts[struct_key]


def test_1d_array_member_has_is_array():
    """A 1D array member should have is_array=True in member_decl_types."""
    code = "struct S { int data[10]; };"
    layout = _get_layout(code, "struct S")
    mdt = layout.member_decl_types
    assert mdt is not None
    ty = mdt["data"]
    assert ty.is_array is True
    assert ty.array_element_type is not None
    assert ty.array_element_type.base == "int"
    assert ty.array_element_type.is_array is False
    assert ty.array_dimensions == [10]


def test_2d_array_member_has_is_array():
    """A 2D array member should have is_array=True with correct dimensions."""
    code = "struct M { int matrix[3][4]; };"
    layout = _get_layout(code, "struct M")
    mdt = layout.member_decl_types
    assert mdt is not None
    ty = mdt["matrix"]
    assert ty.is_array is True
    assert ty.array_dimensions == [3, 4]
    # Element type for 2D array is itself an array type (inner dimension)
    elem = ty.array_element_type
    assert elem is not None
    assert elem.is_array is True
    assert elem.array_dimensions == [4]
    # Inner element type is the scalar
    inner_elem = elem.array_element_type
    assert inner_elem is not None
    assert inner_elem.base == "int"
    assert inner_elem.is_array is False


def test_non_array_member_not_marked():
    """A non-array member should have is_array=False."""
    code = "struct S { int x; char *p; };"
    layout = _get_layout(code, "struct S")
    mdt = layout.member_decl_types
    assert mdt is not None
    assert mdt["x"].is_array is False
    assert mdt["p"].is_array is False


def test_char_array_member():
    """A char array member should have correct element type."""
    code = "struct Buf { char name[32]; };"
    layout = _get_layout(code, "struct Buf")
    mdt = layout.member_decl_types
    assert mdt is not None
    ty = mdt["name"]
    assert ty.is_array is True
    assert ty.array_element_type.base == "char"
    assert ty.array_dimensions == [32]


def test_pointer_array_member():
    """An array of pointers should have pointer element type."""
    code = "struct S { int *ptrs[5]; };"
    layout = _get_layout(code, "struct S")
    mdt = layout.member_decl_types
    assert mdt is not None
    ty = mdt["ptrs"]
    assert ty.is_array is True
    assert ty.array_element_type.is_pointer is True
    assert ty.array_element_type.pointer_level == 1
    assert ty.array_dimensions == [5]


def test_mixed_members():
    """Struct with both array and non-array members."""
    code = "struct Mixed { int count; long data[8]; char *name; };"
    layout = _get_layout(code, "struct Mixed")
    mdt = layout.member_decl_types
    assert mdt is not None
    # count is not an array
    assert mdt["count"].is_array is False
    # data is an array
    assert mdt["data"].is_array is True
    assert "long" in mdt["data"].array_element_type.base
    assert mdt["data"].array_dimensions == [8]
    # name is not an array
    assert mdt["name"].is_array is False
