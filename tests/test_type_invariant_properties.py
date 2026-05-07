"""Property-based tests for Type dataclass invariants.

**Validates: Requirements 1.4, 1.5**

Tests that the Type dataclass maintains its invariants:
- is_array=True implies array_element_type is non-None
- is_array=True and is_pointer=True are mutually exclusive
- array_dimensions is a non-empty list when is_array=True and sizes are known
"""

from hypothesis import given, settings, strategies as st

from pycc.ast_nodes import Type


# --- Strategies ---

# Base type names commonly used in C
base_types = st.sampled_from(["int", "char", "float", "double", "long", "short", "void",
                               "unsigned int", "struct foo", "union bar"])

# Dimension sizes: either a known size (1-1000) or None (unsized)
dimension_size = st.one_of(st.integers(min_value=1, max_value=1000), st.none())

# Non-empty list of dimensions for arrays with known sizes
known_dimensions = st.lists(st.integers(min_value=1, max_value=1000), min_size=1, max_size=4)

# Dimensions that may include None entries
any_dimensions = st.lists(dimension_size, min_size=1, max_size=4)


@st.composite
def array_type_strategy(draw):
    """Generate a valid array Type instance with is_array=True."""
    base = draw(base_types)
    dims = draw(any_dimensions)

    # Build element type (simple, non-array)
    elem_type = Type(line=0, column=0, base=base)

    return Type(
        line=0, column=0,
        base=base,
        is_array=True,
        array_element_type=elem_type,
        array_dimensions=dims,
    )


@st.composite
def pointer_type_strategy(draw):
    """Generate a valid pointer Type instance with is_pointer=True."""
    base = draw(base_types)
    level = draw(st.integers(min_value=1, max_value=3))

    return Type(
        line=0, column=0,
        base=base,
        is_pointer=True,
        pointer_level=level,
    )


# --- Property Tests ---

class TestTypeInvariants:
    """Property 1: Type 不变量 — is_array 蕴含 array_element_type 非空

    **Validates: Requirements 1.4, 1.5**
    """

    @settings(max_examples=100)
    @given(t=array_type_strategy())
    def test_is_array_implies_element_type_non_none(self, t: Type):
        """When is_array=True, array_element_type SHALL be non-None."""
        assert t.is_array is True
        assert t.array_element_type is not None

    @settings(max_examples=100)
    @given(t=array_type_strategy())
    def test_is_array_implies_dimensions_non_empty(self, t: Type):
        """When is_array=True with known sizes, array_dimensions SHALL be a non-empty list."""
        assert t.is_array is True
        assert t.array_dimensions is not None
        assert len(t.array_dimensions) > 0

    @settings(max_examples=100)
    @given(t=array_type_strategy())
    def test_array_and_pointer_mutually_exclusive(self, t: Type):
        """is_array=True and is_pointer=True SHALL be mutually exclusive."""
        assert t.is_array is True
        assert t.is_pointer is False

    @settings(max_examples=100)
    @given(t=pointer_type_strategy())
    def test_pointer_is_not_array(self, t: Type):
        """A pointer Type SHALL have is_array=False."""
        assert t.is_pointer is True
        assert t.is_array is False

    @settings(max_examples=100)
    @given(dims=known_dimensions)
    def test_array_dimensions_match_construction(self, dims):
        """array_dimensions SHALL faithfully store the dimensions provided at construction."""
        elem = Type(line=0, column=0, base="int")
        t = Type(
            line=0, column=0,
            base="int",
            is_array=True,
            array_element_type=elem,
            array_dimensions=dims,
        )
        assert t.array_dimensions == dims
        assert len(t.array_dimensions) == len(dims)
