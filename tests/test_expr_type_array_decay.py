"""Unit tests for array decay in _expr_type(Identifier) using Type.is_array.

Validates that when an Identifier's declared type has is_array=True,
_expr_type returns a pointer-to-element type (array decay).

Requirements: 3.1, 3.5
"""
from __future__ import annotations

import pytest

from pycc.ast_nodes import Type, Identifier, ArrayAccess, UnaryOp
from pycc.semantics import SemanticAnalyzer


def _make_analyzer(**overrides) -> SemanticAnalyzer:
    sa = SemanticAnalyzer()
    sa._scopes = [{}]
    sa._typedefs = [{}]
    sa._layouts = overrides.get("layouts", {})
    sa._function_sigs = overrides.get("function_sigs", {})
    sa._function_full_sig = overrides.get("function_full_sig", {})
    sa._function_param_types = {}
    sa._global_types = {}
    sa._global_decl_types = overrides.get("global_decl_types", {})
    sa._decl_types = overrides.get("decl_types", {})
    sa._enum_constants = {}
    sa._local_array_names = overrides.get("local_array_names", set())
    sa._global_arrays = overrides.get("global_arrays", {})
    sa.errors = []
    sa.warnings = []
    return sa


class TestArrayDecayViaIsArray:
    """Test that _expr_type(Identifier) decays arrays to pointers using is_array."""

    def test_int_array_decays_to_int_pointer(self):
        """int arr[10] in expression context should decay to int *."""
        arr_type = Type(
            base="int", is_array=True,
            array_element_type=Type(base="int", line=0, column=0),
            array_dimensions=[10],
            line=0, column=0,
        )
        sa = _make_analyzer(decl_types={"arr": arr_type})
        expr = Identifier(name="arr", line=1, column=1)
        result = sa._expr_type(expr)
        assert result is not None
        assert result.base == "int"
        assert result.is_pointer is True
        assert result.pointer_level == 1
        assert getattr(result, 'is_array', False) is False

    def test_char_array_decays_to_char_pointer(self):
        """char buf[64] in expression context should decay to char *."""
        arr_type = Type(
            base="char", is_array=True,
            array_element_type=Type(base="char", line=0, column=0),
            array_dimensions=[64],
            line=0, column=0,
        )
        sa = _make_analyzer(decl_types={"buf": arr_type})
        expr = Identifier(name="buf", line=1, column=1)
        result = sa._expr_type(expr)
        assert result is not None
        assert result.base == "char"
        assert result.is_pointer is True
        assert result.pointer_level == 1

    def test_pointer_array_decays_to_double_pointer(self):
        """int *ptrs[5] should decay to int ** (pointer to int*)."""
        elem_type = Type(base="int", is_pointer=True, pointer_level=1, line=0, column=0)
        arr_type = Type(
            base="int", is_array=True,
            array_element_type=elem_type,
            array_dimensions=[5],
            line=0, column=0,
        )
        sa = _make_analyzer(decl_types={"ptrs": arr_type})
        expr = Identifier(name="ptrs", line=1, column=1)
        result = sa._expr_type(expr)
        assert result is not None
        assert result.base == "int"
        assert result.is_pointer is True
        assert result.pointer_level == 2

    def test_const_array_preserves_const(self):
        """const int arr[3] should decay to const int *."""
        arr_type = Type(
            base="int", is_array=True,
            array_element_type=Type(base="int", is_const=True, line=0, column=0),
            array_dimensions=[3],
            line=0, column=0,
        )
        sa = _make_analyzer(decl_types={"arr": arr_type})
        expr = Identifier(name="arr", line=1, column=1)
        result = sa._expr_type(expr)
        assert result is not None
        assert result.base == "int"
        assert result.is_pointer is True
        assert result.pointer_level == 1
        assert result.is_const is True

    def test_unsigned_array_preserves_unsigned(self):
        """unsigned int arr[4] should decay to unsigned int *."""
        arr_type = Type(
            base="int", is_array=True, is_unsigned=True,
            array_element_type=Type(base="int", is_unsigned=True, line=0, column=0),
            array_dimensions=[4],
            line=0, column=0,
        )
        sa = _make_analyzer(decl_types={"arr": arr_type})
        expr = Identifier(name="arr", line=1, column=1)
        result = sa._expr_type(expr)
        assert result is not None
        assert result.is_pointer is True
        assert result.pointer_level == 1
        assert result.is_unsigned is True

    def test_non_array_identifier_not_decayed(self):
        """int x (non-array) should return int without decay."""
        sa = _make_analyzer(decl_types={"x": Type(base="int", line=0, column=0)})
        expr = Identifier(name="x", line=1, column=1)
        result = sa._expr_type(expr)
        assert result is not None
        assert result.base == "int"
        assert result.is_pointer is False
        assert result.pointer_level == 0

    def test_pointer_identifier_not_decayed(self):
        """int *p (pointer, not array) should return int * without decay."""
        sa = _make_analyzer(decl_types={
            "p": Type(base="int", is_pointer=True, pointer_level=1, line=0, column=0)
        })
        expr = Identifier(name="p", line=1, column=1)
        result = sa._expr_type(expr)
        assert result is not None
        assert result.base == "int"
        assert result.is_pointer is True
        assert result.pointer_level == 1

    def test_unsized_array_decays(self):
        """int arr[] (unsized) should still decay to int *."""
        arr_type = Type(
            base="int", is_array=True,
            array_element_type=Type(base="int", line=0, column=0),
            array_dimensions=[None],
            line=0, column=0,
        )
        sa = _make_analyzer(decl_types={"arr": arr_type})
        expr = Identifier(name="arr", line=1, column=1)
        result = sa._expr_type(expr)
        assert result is not None
        assert result.base == "int"
        assert result.is_pointer is True
        assert result.pointer_level == 1

    def test_struct_array_decays_to_struct_pointer(self):
        """struct Point arr[10] should decay to struct Point *."""
        arr_type = Type(
            base="struct Point", is_array=True,
            array_element_type=Type(base="struct Point", line=0, column=0),
            array_dimensions=[10],
            line=0, column=0,
        )
        sa = _make_analyzer(decl_types={"arr": arr_type})
        expr = Identifier(name="arr", line=1, column=1)
        result = sa._expr_type(expr)
        assert result is not None
        assert result.base == "struct Point"
        assert result.is_pointer is True
        assert result.pointer_level == 1

    def test_is_array_takes_priority_over_side_channel(self):
        """When is_array is set, decay uses Type info, not _local_array_names."""
        arr_type = Type(
            base="int", is_array=True,
            array_element_type=Type(base="int", line=0, column=0),
            array_dimensions=[5],
            line=0, column=0,
        )
        # Both is_array and side-channel are set — is_array should take priority
        sa = _make_analyzer(
            decl_types={"arr": arr_type},
            local_array_names={"arr"},
        )
        expr = Identifier(name="arr", line=1, column=1)
        result = sa._expr_type(expr)
        assert result is not None
        assert result.base == "int"
        assert result.is_pointer is True
        assert result.pointer_level == 1

    def test_global_array_decays_via_is_array(self):
        """Global array with is_array=True should decay via global_decl_types."""
        arr_type = Type(
            base="long", is_array=True,
            array_element_type=Type(base="long", line=0, column=0),
            array_dimensions=[8],
            line=0, column=0,
        )
        sa = _make_analyzer(global_decl_types={"data": arr_type})
        expr = Identifier(name="data", line=1, column=1)
        result = sa._expr_type(expr)
        assert result is not None
        assert result.base == "long"
        assert result.is_pointer is True
        assert result.pointer_level == 1
