"""Unit tests for is_array being set on local array declarations.

Validates: Requirements 2.1, 2.5

Tests that _parse_local_declaration correctly sets Type.is_array=True
for local variable declarations with array dimensions inside function bodies,
while preserving backward-compatible array_size/array_dims fields.
Also verifies that function parameters with [] still decay to pointers.
"""

from pycc.ast_nodes import Declaration, FunctionDecl, Type
from pycc.lexer import Lexer
from pycc.parser import Parser


def _parse_function(code: str) -> FunctionDecl:
    """Parse code and return the first FunctionDecl."""
    tokens = Lexer(code).tokenize()
    ast = Parser(tokens).parse()
    for decl in ast.declarations:
        if isinstance(decl, FunctionDecl):
            return decl
    raise AssertionError("No FunctionDecl found in parsed AST")


def _get_local_decl(func: FunctionDecl, name: str) -> Declaration:
    """Find a local declaration by name in a function body."""
    for stmt in func.body.statements:
        if isinstance(stmt, Declaration) and stmt.name == name:
            return stmt
        if isinstance(stmt, list):
            for d in stmt:
                if isinstance(d, Declaration) and d.name == name:
                    return d
    raise AssertionError(f"No local Declaration named '{name}' found")


class TestLocalArrayDeclIsArray:
    """Local array declarations should have type.is_array=True."""

    def test_simple_int_array(self):
        """int arr[10]; inside function -> type.is_array=True"""
        func = _parse_function("void f(void) { int arr[10]; }")
        decl = _get_local_decl(func, "arr")
        assert decl.type.is_array is True
        assert decl.type.array_dimensions == [10]
        assert decl.type.array_element_type is not None
        assert decl.type.array_element_type.base == "int"

    def test_char_array(self):
        """char buf[256]; inside function -> type.is_array=True"""
        func = _parse_function("void f(void) { char buf[256]; }")
        decl = _get_local_decl(func, "buf")
        assert decl.type.is_array is True
        assert decl.type.array_dimensions == [256]
        assert decl.type.array_element_type.base == "char"

    def test_multidimensional_array(self):
        """int matrix[3][4]; -> nested is_array types"""
        func = _parse_function("void f(void) { int matrix[3][4]; }")
        decl = _get_local_decl(func, "matrix")
        assert decl.type.is_array is True
        assert decl.type.array_dimensions == [3, 4]
        inner = decl.type.array_element_type
        assert inner.is_array is True
        assert inner.array_dimensions == [4]
        assert inner.array_element_type.base == "int"

    def test_backward_compat_array_size(self):
        """array_size and array_dims fields are preserved."""
        func = _parse_function("void f(void) { int arr[8]; }")
        decl = _get_local_decl(func, "arr")
        assert decl.array_size == 8
        assert decl.array_dims == [8]
        assert decl.type.is_array is True

    def test_multi_declarator_local_array(self):
        """int a[2], b[3]; -> both have is_array=True"""
        func = _parse_function("void f(void) { int a[2], b[3]; }")
        decl_a = _get_local_decl(func, "a")
        decl_b = _get_local_decl(func, "b")
        assert decl_a.type.is_array is True
        assert decl_a.type.array_dimensions == [2]
        assert decl_b.type.is_array is True
        assert decl_b.type.array_dimensions == [3]

    def test_pointer_not_array(self):
        """int *p; inside function -> is_array=False"""
        func = _parse_function("void f(void) { int *p; }")
        decl = _get_local_decl(func, "p")
        assert decl.type.is_array is False

    def test_static_local_array(self):
        """static int arr[5]; -> is_array=True with storage class"""
        func = _parse_function("void f(void) { static int arr[5]; }")
        decl = _get_local_decl(func, "arr")
        assert decl.type.is_array is True
        assert decl.type.array_dimensions == [5]


class TestFunctionParamNotArray:
    """Function parameters with [] should decay to pointers, not arrays."""

    def test_param_array_decays_to_pointer(self):
        """void f(int arr[]) -> parameter is_array=False (pointer decay)"""
        func = _parse_function("void f(int arr[]) { }")
        param = func.parameters[0]
        assert param.type.is_array is False
        assert param.type.is_pointer is True

    def test_param_sized_array_decays_to_pointer(self):
        """void f(int arr[10]) -> parameter is_array=False (pointer decay)"""
        func = _parse_function("void f(int arr[10]) { }")
        param = func.parameters[0]
        assert param.type.is_array is False
        assert param.type.is_pointer is True
