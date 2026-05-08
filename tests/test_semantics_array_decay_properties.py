"""Property-based tests for array decay semantics in SemanticAnalyzer._expr_type().

**Validates: Requirements 3.1, 3.2, 3.3, 3.5**

Property 4: For any Identifier expression whose declared type has is_array=True,
_expr_type returns a type with is_pointer=True and pointer_level = element_pointer_level + 1.

Property 5: For any ArrayAccess expression where the base's declared type has
is_array=True, _expr_type returns the array's array_element_type.

Property 6: For any ArrayAccess expression where the base type is a pointer
(is_pointer=True, is_array=False), _expr_type returns a type with
pointer_level = base.pointer_level - 1.
"""
from __future__ import annotations

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from pycc.ast_nodes import (
    Type,
    Identifier,
    ArrayAccess,
    IntLiteral,
)
from pycc.semantics import SemanticAnalyzer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_analyzer(**overrides) -> SemanticAnalyzer:
    """Create a SemanticAnalyzer with minimal internal state for _expr_type() testing."""
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
    sa.errors = []
    sa.warnings = []
    return sa


# ---------------------------------------------------------------------------
# Strategies (smart generators)
# ---------------------------------------------------------------------------

_C89_BASE_TYPES = [
    "int", "char", "short", "long", "float", "double",
    "unsigned int", "unsigned char", "unsigned short", "unsigned long",
    "struct Point", "struct Node",
]

_base_type_st = st.sampled_from(_C89_BASE_TYPES)

# Element pointer level: 0 means plain type, 1+ means pointer element
_elem_pointer_level_st = st.integers(min_value=0, max_value=3)

# Array dimension sizes
_dim_size_st = st.integers(min_value=1, max_value=100)
_dims_st = st.lists(_dim_size_st, min_size=1, max_size=3)

# Variable names
_var_name_st = st.sampled_from(["arr", "buf", "data", "matrix", "vals", "items", "tab"])

# Pointer levels for pointer subscript tests (must be >= 1)
_ptr_level_st = st.integers(min_value=1, max_value=4)


@st.composite
def array_type_and_var(draw):
    """Generate an array Type with a variable name for testing decay.

    Returns (var_name, array_type, element_type) where:
    - array_type has is_array=True
    - element_type is the array_element_type (may itself be a pointer)
    """
    base = draw(_base_type_st)
    elem_ptr_level = draw(_elem_pointer_level_st)
    dims = draw(_dims_st)
    var_name = draw(_var_name_st)

    # Build element type
    elem_type = Type(
        base=base,
        is_pointer=elem_ptr_level > 0,
        pointer_level=elem_ptr_level,
        line=0, column=0,
    )

    # Build array type
    arr_type = Type(
        base=base,
        is_array=True,
        array_element_type=elem_type,
        array_dimensions=dims,
        line=0, column=0,
    )

    return var_name, arr_type, elem_type


@st.composite
def pointer_type_and_var(draw):
    """Generate a pointer Type (not array) with a variable name for testing subscript.

    Returns (var_name, pointer_type) where:
    - pointer_type has is_pointer=True, is_array=False, pointer_level >= 1
    """
    base = draw(_base_type_st)
    ptr_level = draw(_ptr_level_st)
    var_name = draw(_var_name_st)

    ptr_type = Type(
        base=base,
        is_pointer=True,
        pointer_level=ptr_level,
        is_array=False,
        line=0, column=0,
    )

    return var_name, ptr_type


# ---------------------------------------------------------------------------
# Property Tests
# ---------------------------------------------------------------------------

class TestProperty4ArrayDecayToPointer:
    """Feature: array-pointer-distinction, Property 4: Array identifier decays to pointer

    For any Identifier expression whose declared type has is_array=True,
    _expr_type returns a type with is_pointer=True and
    pointer_level = element_pointer_level + 1.

    **Validates: Requirements 3.1, 3.5**
    """

    @settings(max_examples=100)
    @given(data=array_type_and_var())
    def test_array_identifier_decays_to_pointer(self, data):
        """Feature: array-pointer-distinction, Property 4: Array identifier decays to pointer"""
        var_name, arr_type, elem_type = data

        sa = _make_analyzer(decl_types={var_name: arr_type})
        expr = Identifier(name=var_name, line=1, column=1)
        result = sa._expr_type(expr)

        # The result must be a pointer type
        assert result is not None, (
            f"_expr_type returned None for array identifier '{var_name}' "
            f"with type {arr_type}"
        )
        assert result.is_pointer is True, (
            f"Expected is_pointer=True after decay, got {result.is_pointer} "
            f"for array type base={arr_type.base}, elem_ptr_level={elem_type.pointer_level}"
        )

        # pointer_level = element_pointer_level + 1
        expected_level = (getattr(elem_type, 'pointer_level', 0) or 0) + 1
        assert result.pointer_level == expected_level, (
            f"Expected pointer_level={expected_level} after decay, "
            f"got {result.pointer_level}. "
            f"Element pointer_level={elem_type.pointer_level}"
        )

        # Base type should match element base
        assert result.base == elem_type.base, (
            f"Expected base='{elem_type.base}' after decay, got '{result.base}'"
        )

        # Result should NOT be an array
        assert getattr(result, 'is_array', False) is False, (
            "Decayed type should not be an array"
        )

    @settings(max_examples=100)
    @given(data=array_type_and_var())
    def test_global_array_identifier_decays_to_pointer(self, data):
        """Feature: array-pointer-distinction, Property 4: Global array decay"""
        var_name, arr_type, elem_type = data

        # Use global_decl_types instead of local decl_types
        sa = _make_analyzer(global_decl_types={var_name: arr_type})
        expr = Identifier(name=var_name, line=1, column=1)
        result = sa._expr_type(expr)

        assert result is not None
        assert result.is_pointer is True
        expected_level = (getattr(elem_type, 'pointer_level', 0) or 0) + 1
        assert result.pointer_level == expected_level


class TestProperty5ArraySubscriptReturnsElementType:
    """Feature: array-pointer-distinction, Property 5: Array subscript returns element type

    For any ArrayAccess expression where the base's declared type has
    is_array=True, _expr_type returns the array's array_element_type.

    **Validates: Requirements 3.2**
    """

    @settings(max_examples=100)
    @given(data=array_type_and_var())
    def test_array_subscript_returns_element_type(self, data):
        """Feature: array-pointer-distinction, Property 5: Array subscript returns element type"""
        var_name, arr_type, elem_type = data

        sa = _make_analyzer(decl_types={var_name: arr_type})

        # Build ArrayAccess: var_name[0]
        expr = ArrayAccess(
            array=Identifier(name=var_name, line=1, column=1),
            index=IntLiteral(value=0, line=1, column=5),
            line=1, column=1,
        )
        result = sa._expr_type(expr)

        assert result is not None, (
            f"_expr_type returned None for array subscript '{var_name}[0]' "
            f"with array type base={arr_type.base}"
        )

        # Result should be equivalent to the element type
        assert result.base == elem_type.base, (
            f"Expected base='{elem_type.base}' from subscript, got '{result.base}'"
        )
        assert result.is_pointer == elem_type.is_pointer, (
            f"Expected is_pointer={elem_type.is_pointer} from subscript, "
            f"got {result.is_pointer}"
        )
        assert (getattr(result, 'pointer_level', 0) or 0) == (getattr(elem_type, 'pointer_level', 0) or 0), (
            f"Expected pointer_level={elem_type.pointer_level} from subscript, "
            f"got {result.pointer_level}"
        )

    @settings(max_examples=100)
    @given(data=array_type_and_var())
    def test_global_array_subscript_returns_element_type(self, data):
        """Feature: array-pointer-distinction, Property 5: Global array subscript"""
        var_name, arr_type, elem_type = data

        sa = _make_analyzer(global_decl_types={var_name: arr_type})

        expr = ArrayAccess(
            array=Identifier(name=var_name, line=1, column=1),
            index=IntLiteral(value=0, line=1, column=5),
            line=1, column=1,
        )
        result = sa._expr_type(expr)

        assert result is not None
        assert result.base == elem_type.base
        assert (getattr(result, 'pointer_level', 0) or 0) == (getattr(elem_type, 'pointer_level', 0) or 0)


class TestProperty6PointerSubscriptDereferences:
    """Feature: array-pointer-distinction, Property 6: Pointer subscript dereferences

    For any ArrayAccess expression where the base type is a pointer
    (is_pointer=True, is_array=False), _expr_type returns a type with
    pointer_level = base.pointer_level - 1.

    **Validates: Requirements 3.3**
    """

    @settings(max_examples=100)
    @given(data=pointer_type_and_var())
    def test_pointer_subscript_decrements_pointer_level(self, data):
        """Feature: array-pointer-distinction, Property 6: Pointer subscript dereferences"""
        var_name, ptr_type = data

        sa = _make_analyzer(decl_types={var_name: ptr_type})

        # Build ArrayAccess: var_name[0]
        expr = ArrayAccess(
            array=Identifier(name=var_name, line=1, column=1),
            index=IntLiteral(value=0, line=1, column=5),
            line=1, column=1,
        )
        result = sa._expr_type(expr)

        assert result is not None, (
            f"_expr_type returned None for pointer subscript '{var_name}[0]' "
            f"with pointer type base={ptr_type.base}, level={ptr_type.pointer_level}"
        )

        # pointer_level should be decremented by 1
        expected_level = ptr_type.pointer_level - 1
        assert (getattr(result, 'pointer_level', 0) or 0) == expected_level, (
            f"Expected pointer_level={expected_level} after dereference, "
            f"got {result.pointer_level}. "
            f"Base pointer_level={ptr_type.pointer_level}"
        )

        # is_pointer should be True only if pointer_level > 0
        expected_is_pointer = expected_level > 0
        assert result.is_pointer == expected_is_pointer, (
            f"Expected is_pointer={expected_is_pointer} after dereference, "
            f"got {result.is_pointer}"
        )

        # Base type should be preserved
        assert result.base == ptr_type.base, (
            f"Expected base='{ptr_type.base}' after dereference, got '{result.base}'"
        )

    @settings(max_examples=100)
    @given(data=pointer_type_and_var())
    def test_global_pointer_subscript_decrements_pointer_level(self, data):
        """Feature: array-pointer-distinction, Property 6: Global pointer subscript"""
        var_name, ptr_type = data

        sa = _make_analyzer(global_decl_types={var_name: ptr_type})

        expr = ArrayAccess(
            array=Identifier(name=var_name, line=1, column=1),
            index=IntLiteral(value=0, line=1, column=5),
            line=1, column=1,
        )
        result = sa._expr_type(expr)

        assert result is not None
        expected_level = ptr_type.pointer_level - 1
        assert (getattr(result, 'pointer_level', 0) or 0) == expected_level
        assert result.base == ptr_type.base
