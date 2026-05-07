"""Unit tests for _build_array_type helper function.

Validates: Requirements 1.4, 1.5, 2.4

Tests that _build_array_type correctly constructs array Type instances
for 1D arrays, multi-dimensional arrays, pointer arrays, and unsized arrays.
"""

from pycc.ast_nodes import Type
from pycc.parser import _build_array_type


class TestBuildArrayType1D:
    """Tests for one-dimensional array construction."""

    def test_simple_int_array(self):
        """int arr[10] -> Type(is_array=True, elem=Type(base='int'), dims=[10])"""
        base = Type(line=1, column=0, base="int")
        result = _build_array_type(base, [10])

        assert result.is_array is True
        assert result.array_dimensions == [10]
        assert result.array_element_type is not None
        assert result.array_element_type.base == "int"
        assert result.array_element_type.is_array is False
        assert result.array_element_type.is_pointer is False
        assert result.base == "int"

    def test_unsized_array(self):
        """char s[] -> Type(is_array=True, elem=Type(base='char'), dims=[None])"""
        base = Type(line=1, column=0, base="char")
        result = _build_array_type(base, [None])

        assert result.is_array is True
        assert result.array_dimensions == [None]
        assert result.array_element_type is not None
        assert result.array_element_type.base == "char"

    def test_pointer_array(self):
        """int *ptrs[5] -> Type(is_array=True, elem=Type(is_pointer=True, pointer_level=1))"""
        base = Type(line=1, column=0, base="int", is_pointer=True, pointer_level=1)
        result = _build_array_type(base, [5])

        assert result.is_array is True
        assert result.array_dimensions == [5]
        elem = result.array_element_type
        assert elem is not None
        assert elem.base == "int"
        assert elem.is_pointer is True
        assert elem.pointer_level == 1
        assert elem.is_array is False

    def test_const_array(self):
        """const int arr[3] -> element preserves is_const"""
        base = Type(line=1, column=0, base="int", is_const=True)
        result = _build_array_type(base, [3])

        assert result.is_array is True
        assert result.array_element_type.is_const is True

    def test_preserves_line_column(self):
        """Line and column info should be preserved."""
        base = Type(line=42, column=7, base="float")
        result = _build_array_type(base, [8])

        assert result.line == 42
        assert result.column == 7
        assert result.array_element_type.line == 42
        assert result.array_element_type.column == 7


class TestBuildArrayTypeMultiDim:
    """Tests for multi-dimensional array construction."""

    def test_2d_array(self):
        """int m[3][4] -> nested array types."""
        base = Type(line=1, column=0, base="int")
        result = _build_array_type(base, [3, 4])

        # Outermost: is_array=True, dims=[3,4]
        assert result.is_array is True
        assert result.array_dimensions == [3, 4]
        assert result.base == "int"

        # Inner: is_array=True, dims=[4], elem=Type(base="int")
        inner = result.array_element_type
        assert inner is not None
        assert inner.is_array is True
        assert inner.array_dimensions == [4]
        assert inner.base == "int"

        # Leaf: plain int
        leaf = inner.array_element_type
        assert leaf is not None
        assert leaf.base == "int"
        assert leaf.is_array is False

    def test_3d_array(self):
        """int cube[2][3][4] -> doubly nested array types."""
        base = Type(line=1, column=0, base="int")
        result = _build_array_type(base, [2, 3, 4])

        assert result.is_array is True
        assert result.array_dimensions == [2, 3, 4]

        # Second level: dims=[3]
        mid = result.array_element_type
        assert mid.is_array is True
        assert mid.array_dimensions == [3]

        # Third level: dims=[4]
        inner = mid.array_element_type
        assert inner.is_array is True
        assert inner.array_dimensions == [4]

        # Leaf
        leaf = inner.array_element_type
        assert leaf.base == "int"
        assert leaf.is_array is False

    def test_2d_pointer_array(self):
        """int *m[2][3] -> nested arrays with pointer element."""
        base = Type(line=1, column=0, base="int", is_pointer=True, pointer_level=1)
        result = _build_array_type(base, [2, 3])

        assert result.is_array is True
        assert result.array_dimensions == [2, 3]

        inner = result.array_element_type
        assert inner.is_array is True
        assert inner.array_dimensions == [3]

        leaf = inner.array_element_type
        assert leaf.is_pointer is True
        assert leaf.pointer_level == 1
        assert leaf.is_array is False


class TestBuildArrayTypeEdgeCases:
    """Edge cases and special scenarios."""

    def test_empty_dims_returns_base(self):
        """Empty dims list should return the base type unchanged."""
        base = Type(line=1, column=0, base="int")
        result = _build_array_type(base, [])

        assert result is base  # Same object returned

    def test_unsigned_type_preserved(self):
        """unsigned long arr[4] -> element preserves is_unsigned."""
        base = Type(line=1, column=0, base="long", is_unsigned=True)
        result = _build_array_type(base, [4])

        assert result.array_element_type.is_unsigned is True
        assert result.array_element_type.base == "long"

    def test_fn_pointer_array(self):
        """Function pointer info preserved in element type."""
        base = Type(line=1, column=0, base="int", is_pointer=True, pointer_level=1,
                    fn_param_count=2)
        result = _build_array_type(base, [10])

        elem = result.array_element_type
        assert elem.fn_param_count == 2
        assert elem.is_pointer is True
