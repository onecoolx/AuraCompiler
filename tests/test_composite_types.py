"""Tests for types_compatible() — C89 §6.1.2.6 type compatibility.

Covers basic types, pointer types, array types, and function types.
"""

import pytest
from pycc.ast_nodes import Type
from pycc.semantics import types_compatible, composite_type


# ── Basic type compatibility ──────────────────────────────────────────


class TestBasicTypeCompatibility:
    """Same canonical type is compatible; different types are not."""

    def test_same_int(self):
        t1 = Type(base="int", line=0, column=0)
        t2 = Type(base="int", line=0, column=0)
        assert types_compatible(t1, t2) is True

    def test_int_and_signed_int(self):
        """C89: 'int' and 'signed int' are the same type."""
        t1 = Type(base="int", line=0, column=0)
        t2 = Type(base="int", is_signed=True, line=0, column=0)
        assert types_compatible(t1, t2) is True

    def test_signed_int_synonym(self):
        t1 = Type(base="signed int", line=0, column=0)
        t2 = Type(base="int", line=0, column=0)
        assert types_compatible(t1, t2) is True

    def test_unsigned_int_synonym(self):
        t1 = Type(base="unsigned", line=0, column=0)
        t2 = Type(base="unsigned int", line=0, column=0)
        assert types_compatible(t1, t2) is True

    def test_int_vs_char_incompatible(self):
        t1 = Type(base="int", line=0, column=0)
        t2 = Type(base="char", line=0, column=0)
        assert types_compatible(t1, t2) is False

    def test_int_vs_unsigned_int_incompatible(self):
        t1 = Type(base="int", line=0, column=0)
        t2 = Type(base="unsigned int", line=0, column=0)
        assert types_compatible(t1, t2) is False

    def test_same_char(self):
        t1 = Type(base="char", line=0, column=0)
        t2 = Type(base="char", line=0, column=0)
        assert types_compatible(t1, t2) is True

    def test_same_double(self):
        t1 = Type(base="double", line=0, column=0)
        t2 = Type(base="double", line=0, column=0)
        assert types_compatible(t1, t2) is True

    def test_float_vs_double_incompatible(self):
        t1 = Type(base="float", line=0, column=0)
        t2 = Type(base="double", line=0, column=0)
        assert types_compatible(t1, t2) is False

    def test_long_synonyms(self):
        t1 = Type(base="long", line=0, column=0)
        t2 = Type(base="long int", line=0, column=0)
        assert types_compatible(t1, t2) is True

    def test_short_synonyms(self):
        t1 = Type(base="short", line=0, column=0)
        t2 = Type(base="short int", line=0, column=0)
        assert types_compatible(t1, t2) is True

    def test_same_struct(self):
        t1 = Type(base="struct S", line=0, column=0)
        t2 = Type(base="struct S", line=0, column=0)
        assert types_compatible(t1, t2) is True

    def test_different_struct_incompatible(self):
        t1 = Type(base="struct A", line=0, column=0)
        t2 = Type(base="struct B", line=0, column=0)
        assert types_compatible(t1, t2) is False

    def test_void_types(self):
        t1 = Type(base="void", line=0, column=0)
        t2 = Type(base="void", line=0, column=0)
        assert types_compatible(t1, t2) is True

    def test_string_shorthand(self):
        """Plain strings are accepted as a convenience."""
        assert types_compatible("int", "int") is True
        assert types_compatible("int", "char") is False

    def test_none_is_compatible(self):
        """None (unknown type) is always compatible."""
        t = Type(base="int", line=0, column=0)
        assert types_compatible(None, t) is True
        assert types_compatible(t, None) is True
        assert types_compatible(None, None) is True


# ── Pointer type compatibility ────────────────────────────────────────


class TestPointerTypeCompatibility:
    """Pointers to compatible types are compatible."""

    def test_same_pointer(self):
        t1 = Type(base="int", is_pointer=True, pointer_level=1, line=0, column=0)
        t2 = Type(base="int", is_pointer=True, pointer_level=1, line=0, column=0)
        assert types_compatible(t1, t2) is True

    def test_pointer_to_different_base_incompatible(self):
        t1 = Type(base="int", is_pointer=True, pointer_level=1, line=0, column=0)
        t2 = Type(base="char", is_pointer=True, pointer_level=1, line=0, column=0)
        assert types_compatible(t1, t2) is False

    def test_void_pointer_compatible_with_any(self):
        t1 = Type(base="void", is_pointer=True, pointer_level=1, line=0, column=0)
        t2 = Type(base="int", is_pointer=True, pointer_level=1, line=0, column=0)
        assert types_compatible(t1, t2) is True
        assert types_compatible(t2, t1) is True

    def test_pointer_vs_non_pointer_incompatible(self):
        t1 = Type(base="int", is_pointer=True, pointer_level=1, line=0, column=0)
        t2 = Type(base="int", line=0, column=0)
        assert types_compatible(t1, t2) is False

    def test_different_pointer_levels_incompatible(self):
        t1 = Type(base="int", is_pointer=True, pointer_level=1, line=0, column=0)
        t2 = Type(base="int", is_pointer=True, pointer_level=2, line=0, column=0)
        assert types_compatible(t1, t2) is False

    def test_double_pointer_compatible(self):
        t1 = Type(base="int", is_pointer=True, pointer_level=2, line=0, column=0)
        t2 = Type(base="int", is_pointer=True, pointer_level=2, line=0, column=0)
        assert types_compatible(t1, t2) is True

    def test_pointer_to_signed_int_synonym(self):
        """int* and signed int* should be compatible."""
        t1 = Type(base="int", is_pointer=True, pointer_level=1, line=0, column=0)
        t2 = Type(base="signed int", is_pointer=True, pointer_level=1, line=0, column=0)
        assert types_compatible(t1, t2) is True


# ── Array type compatibility ──────────────────────────────────────────


class TestArrayTypeCompatibility:
    """Element types compatible AND (sizes equal OR at least one unspecified)."""

    def _arr_type(self, base, size=None, **kw):
        """Helper to create a Type with array_size attribute."""
        t = Type(base=base, line=0, column=0, **kw)
        t.array_size = size
        return t

    def test_same_array(self):
        t1 = self._arr_type("int", 10)
        t2 = self._arr_type("int", 10)
        assert types_compatible(t1, t2) is True

    def test_different_sizes_incompatible(self):
        t1 = self._arr_type("int", 10)
        t2 = self._arr_type("int", 20)
        assert types_compatible(t1, t2) is False

    def test_one_unsized_compatible(self):
        t1 = self._arr_type("int", 10)
        t2 = self._arr_type("int", None)
        assert types_compatible(t1, t2) is True

    def test_both_unsized_compatible(self):
        t1 = self._arr_type("int", None)
        t2 = self._arr_type("int", None)
        assert types_compatible(t1, t2) is True

    def test_different_element_types_incompatible(self):
        t1 = self._arr_type("int", 10)
        t2 = self._arr_type("char", 10)
        assert types_compatible(t1, t2) is False

    def test_element_type_synonyms_compatible(self):
        t1 = self._arr_type("long", 5)
        t2 = self._arr_type("long int", 5)
        assert types_compatible(t1, t2) is True


# ── Function type compatibility ───────────────────────────────────────


class TestFunctionTypeCompatibility:
    """Return type compatible AND parameter types compatible."""

    def _fn_type(self, ret_base, param_bases):
        """Helper to create a Type with function signature metadata."""
        ret = Type(base=ret_base, line=0, column=0)
        params = [Type(base=b, line=0, column=0) for b in param_bases]
        t = Type(base=ret_base, line=0, column=0,
                 fn_return_type=ret, fn_param_types=params,
                 fn_param_count=len(params))
        return t

    def test_same_function_type(self):
        t1 = self._fn_type("int", ["int", "char"])
        t2 = self._fn_type("int", ["int", "char"])
        assert types_compatible(t1, t2) is True

    def test_different_return_type_incompatible(self):
        t1 = self._fn_type("int", ["int"])
        t2 = self._fn_type("void", ["int"])
        assert types_compatible(t1, t2) is False

    def test_different_param_type_incompatible(self):
        t1 = self._fn_type("int", ["int", "char"])
        t2 = self._fn_type("int", ["int", "double"])
        assert types_compatible(t1, t2) is False

    def test_different_param_count_incompatible(self):
        t1 = self._fn_type("int", ["int"])
        t2 = self._fn_type("int", ["int", "char"])
        assert types_compatible(t1, t2) is False

    def test_no_params_compatible(self):
        t1 = self._fn_type("int", [])
        t2 = self._fn_type("int", [])
        assert types_compatible(t1, t2) is True

    def test_param_synonym_compatible(self):
        """int and signed int parameters should be compatible."""
        t1 = self._fn_type("int", ["int"])
        ret2 = Type(base="int", line=0, column=0)
        p2 = Type(base="signed int", line=0, column=0)
        t2 = Type(base="int", line=0, column=0,
                  fn_return_type=ret2, fn_param_types=[p2], fn_param_count=1)
        assert types_compatible(t1, t2) is True

    def test_one_side_no_param_info_compatible(self):
        """C89: old-style decl without prototype is compatible with prototype."""
        t1 = self._fn_type("int", ["int", "char"])
        # t2 has return type info but no param list (old-style)
        t2 = Type(base="int", line=0, column=0,
                  fn_return_type=Type(base="int", line=0, column=0),
                  fn_param_types=None, fn_param_count=None)
        assert types_compatible(t1, t2) is True


# ── composite_type() tests ────────────────────────────────────────────


class TestCompositeTypeBasic:
    """Composite of two compatible basic types returns canonical form."""

    def test_same_int(self):
        t1 = Type(base="int", line=0, column=0)
        t2 = Type(base="int", line=0, column=0)
        ct = composite_type(t1, t2)
        assert ct.base == "int"

    def test_int_and_signed_int(self):
        """Composite of 'int' and 'signed int' is canonical 'int'."""
        t1 = Type(base="int", line=0, column=0)
        t2 = Type(base="int", is_signed=True, line=0, column=0)
        ct = composite_type(t1, t2)
        assert ct.base == "int"

    def test_long_synonyms(self):
        t1 = Type(base="long", line=0, column=0)
        t2 = Type(base="long int", line=0, column=0)
        ct = composite_type(t1, t2)
        assert ct.base == "long"

    def test_none_returns_other(self):
        t = Type(base="int", line=0, column=0)
        assert composite_type(None, t) is t
        assert composite_type(t, None) is t

    def test_both_none(self):
        assert composite_type(None, None) is None

    def test_string_shorthand(self):
        ct = composite_type("int", "int")
        assert ct.base == "int"


class TestCompositeTypeArray:
    """Composite of array types merges size information."""

    def _arr_type(self, base, size=None, **kw):
        t = Type(base=base, line=0, column=0, **kw)
        t.array_size = size
        return t

    def test_sized_and_unsized(self):
        """int[10] + int[] → int[10]."""
        t1 = self._arr_type("int", 10)
        t2 = self._arr_type("int", None)
        ct = composite_type(t1, t2)
        assert ct.array_size == 10

    def test_unsized_and_sized(self):
        """int[] + int[10] → int[10]."""
        t1 = self._arr_type("int", None)
        t2 = self._arr_type("int", 10)
        ct = composite_type(t1, t2)
        assert ct.array_size == 10

    def test_both_sized_same(self):
        t1 = self._arr_type("int", 5)
        t2 = self._arr_type("int", 5)
        ct = composite_type(t1, t2)
        assert ct.array_size == 5

    def test_both_unsized(self):
        t1 = self._arr_type("int", None)
        t2 = self._arr_type("int", None)
        ct = composite_type(t1, t2)
        assert ct.array_size is None

    def test_preserves_base_type(self):
        t1 = self._arr_type("char", 20)
        t2 = self._arr_type("char", None)
        ct = composite_type(t1, t2)
        assert ct.base == "char"
        assert ct.array_size == 20


class TestCompositeTypeFunction:
    """Composite of function types merges parameter info."""

    def _fn_type(self, ret_base, param_bases=None):
        ret = Type(base=ret_base, line=0, column=0)
        params = [Type(base=b, line=0, column=0) for b in param_bases] if param_bases is not None else None
        t = Type(base=ret_base, line=0, column=0,
                 fn_return_type=ret,
                 fn_param_types=params,
                 fn_param_count=len(params) if params is not None else None)
        return t

    def test_both_have_params(self):
        t1 = self._fn_type("int", ["int", "char"])
        t2 = self._fn_type("int", ["int", "char"])
        ct = composite_type(t1, t2)
        assert ct.fn_param_count == 2
        assert ct.fn_param_types is not None
        assert len(ct.fn_param_types) == 2

    def test_one_has_params_other_doesnt(self):
        """Prototyped + old-style → composite has the parameter info."""
        t1 = self._fn_type("int", ["int", "char"])
        t2 = self._fn_type("int", None)  # old-style, no param info
        ct = composite_type(t1, t2)
        assert ct.fn_param_types is not None
        assert len(ct.fn_param_types) == 2

    def test_reverse_one_has_params(self):
        """old-style + prototyped → composite has the parameter info."""
        t1 = self._fn_type("int", None)
        t2 = self._fn_type("int", ["double"])
        ct = composite_type(t1, t2)
        assert ct.fn_param_types is not None
        assert len(ct.fn_param_types) == 1

    def test_composite_return_type(self):
        t1 = self._fn_type("int", ["int"])
        t2 = self._fn_type("int", ["int"])
        ct = composite_type(t1, t2)
        assert ct.fn_return_type is not None
        assert ct.fn_return_type.base == "int"

    def test_no_params_both_sides(self):
        t1 = self._fn_type("void", [])
        t2 = self._fn_type("void", [])
        ct = composite_type(t1, t2)
        assert ct.fn_param_types == []
        assert ct.fn_param_count == 0


class TestCompositeTypePointer:
    """Composite of pointer types."""

    def test_same_pointer(self):
        t1 = Type(base="int", is_pointer=True, pointer_level=1, line=0, column=0)
        t2 = Type(base="int", is_pointer=True, pointer_level=1, line=0, column=0)
        ct = composite_type(t1, t2)
        assert ct.is_pointer is True
        assert ct.pointer_level == 1
        assert ct.base == "int"

    def test_pointer_to_function_merges_params(self):
        """Pointer to function with params + pointer to function without → keeps params."""
        t1 = Type(base="int", is_pointer=True, pointer_level=1,
                  fn_return_type=Type(base="int", line=0, column=0),
                  fn_param_types=[Type(base="int", line=0, column=0)],
                  fn_param_count=1, line=0, column=0)
        t2 = Type(base="int", is_pointer=True, pointer_level=1,
                  fn_return_type=Type(base="int", line=0, column=0),
                  fn_param_types=None, fn_param_count=None,
                  line=0, column=0)
        ct = composite_type(t1, t2)
        assert ct.is_pointer is True
        assert ct.fn_param_types is not None
        assert len(ct.fn_param_types) == 1
