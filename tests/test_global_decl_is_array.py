"""Unit tests for is_array being set on global array declarations.

Validates: Requirements 2.2

Tests that _parse_external_declaration correctly sets Type.is_array=True
for global variable declarations with array dimensions, while preserving
backward-compatible array_size/array_dims fields.
"""

from pycc.ast_nodes import Declaration, Type
from pycc.lexer import Lexer
from pycc.parser import Parser


def _parse_global_decl(code: str) -> Declaration:
    """Parse code and return the first Declaration (non-function)."""
    tokens = Lexer(code).tokenize()
    ast = Parser(tokens).parse()
    for decl in ast.declarations:
        if isinstance(decl, Declaration):
            return decl
    raise AssertionError("No Declaration found in parsed AST")


class TestGlobalArrayDeclIsArray:
    """Global array declarations should have type.is_array=True."""

    def test_simple_int_array(self):
        """int arr[10]; -> type.is_array=True, element is int"""
        decl = _parse_global_decl("int arr[10];")
        assert decl.type.is_array is True
        assert decl.type.array_dimensions == [10]
        assert decl.type.array_element_type is not None
        assert decl.type.array_element_type.base == "int"
        assert decl.type.array_element_type.is_array is False

    def test_char_array(self):
        """char buf[256]; -> type.is_array=True"""
        decl = _parse_global_decl("char buf[256];")
        assert decl.type.is_array is True
        assert decl.type.array_dimensions == [256]
        assert decl.type.array_element_type.base == "char"

    def test_unsized_array(self):
        """int arr[]; -> type.is_array=True, dims=[None]"""
        decl = _parse_global_decl('int arr[] = {1, 2, 3};')
        assert decl.type.is_array is True
        assert decl.type.array_dimensions == [None]

    def test_pointer_array(self):
        """int *ptrs[5]; -> is_array=True, element is int pointer"""
        decl = _parse_global_decl("int *ptrs[5];")
        assert decl.type.is_array is True
        assert decl.type.array_dimensions == [5]
        elem = decl.type.array_element_type
        assert elem.is_pointer is True
        assert elem.pointer_level == 1
        assert elem.base == "int"

    def test_2d_array(self):
        """int m[3][4]; -> nested array types"""
        decl = _parse_global_decl("int m[3][4];")
        assert decl.type.is_array is True
        assert decl.type.array_dimensions == [3, 4]
        inner = decl.type.array_element_type
        assert inner.is_array is True
        assert inner.array_dimensions == [4]
        leaf = inner.array_element_type
        assert leaf.base == "int"
        assert leaf.is_array is False

    def test_const_array(self):
        """const int arr[8]; -> is_array=True, element is const"""
        decl = _parse_global_decl("const int arr[8];")
        assert decl.type.is_array is True
        assert decl.type.array_element_type.is_const is True


class TestGlobalNonArrayDeclNotIsArray:
    """Global non-array declarations should have type.is_array=False."""

    def test_simple_int(self):
        """int x; -> is_array=False"""
        decl = _parse_global_decl("int x;")
        assert decl.type.is_array is False

    def test_pointer(self):
        """int *p; -> is_array=False"""
        decl = _parse_global_decl("int *p;")
        assert decl.type.is_array is False
        assert decl.type.is_pointer is True


class TestGlobalArrayBackwardCompat:
    """Backward compatibility: array_size and array_dims fields preserved."""

    def test_array_size_preserved(self):
        """int arr[10]; -> decl.array_size == 10"""
        decl = _parse_global_decl("int arr[10];")
        assert decl.array_size == 10

    def test_array_dims_preserved(self):
        """int m[3][4]; -> decl.array_dims == [3, 4]"""
        decl = _parse_global_decl("int m[3][4];")
        assert decl.array_dims == [3, 4]

    def test_no_array_fields_for_scalar(self):
        """int x; -> decl.array_size is None, decl.array_dims is None"""
        decl = _parse_global_decl("int x;")
        assert decl.array_size is None
        assert decl.array_dims is None


class TestGlobalMultiDeclaratorArray:
    """Multi-declarator globals: int a[2], b[3];"""

    def test_multi_decl_both_arrays(self):
        """int a[2], b[3]; -> both have is_array=True"""
        tokens = Lexer("int a[2], b[3];").tokenize()
        ast = Parser(tokens).parse()
        decls = [d for d in ast.declarations if isinstance(d, Declaration)]
        assert len(decls) == 2
        assert decls[0].name == "a"
        assert decls[0].type.is_array is True
        assert decls[0].type.array_dimensions == [2]
        assert decls[1].name == "b"
        assert decls[1].type.is_array is True
        assert decls[1].type.array_dimensions == [3]

    def test_multi_decl_mixed(self):
        """int x, arr[5]; -> x is not array, arr is array"""
        tokens = Lexer("int x, arr[5];").tokenize()
        ast = Parser(tokens).parse()
        decls = [d for d in ast.declarations if isinstance(d, Declaration)]
        assert len(decls) == 2
        assert decls[0].name == "x"
        assert decls[0].type.is_array is False
        assert decls[1].name == "arr"
        assert decls[1].type.is_array is True
        assert decls[1].type.array_dimensions == [5]
