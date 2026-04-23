"""Property-based tests for the SysV ABI StructClassifier.

**Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5**

Property 3: Struct by-value parameter passing preserves member values
Using Hypothesis, generate random struct layouts with various member types
and sizes, then verify the classifier invariants hold for all inputs.
"""

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from pycc.codegen import (
    EightbyteClass,
    classify_struct,
    get_struct_pass_mode,
    _classify_field,
    _merge_classes,
)
from pycc.semantics import StructLayout


# ---------------------------------------------------------------------------
# Hypothesis strategies for generating random struct layouts
# ---------------------------------------------------------------------------

# Scalar types with their (size, alignment) on x86-64
INTEGER_TYPES = [
    ("char", 1, 1),
    ("signed char", 1, 1),
    ("unsigned char", 1, 1),
    ("short", 2, 2),
    ("unsigned short", 2, 2),
    ("int", 4, 4),
    ("unsigned int", 4, 4),
    ("long", 8, 8),
    ("unsigned long", 8, 8),
    ("int*", 8, 8),
    ("char*", 8, 8),
]

FLOAT_TYPES = [
    ("float", 4, 4),
    ("double", 8, 8),
]

ALL_SCALAR_TYPES = INTEGER_TYPES + FLOAT_TYPES

# long double is special — causes MEMORY classification
LONG_DOUBLE_TYPE = ("long double", 16, 16)


def _align_up(offset: int, align: int) -> int:
    """Round *offset* up to the next multiple of *align*."""
    return (offset + align - 1) // align * align


@st.composite
def struct_layout_strategy(draw, type_pool=ALL_SCALAR_TYPES, min_members=1, max_members=6):
    """Generate a random StructLayout with members drawn from *type_pool*."""
    num_members = draw(st.integers(min_value=min_members, max_value=max_members))
    members = []
    for i in range(num_members):
        type_name, size, align = draw(st.sampled_from(type_pool))
        members.append((f"m{i}", type_name, size, align))

    # Compute offsets respecting alignment (C struct layout rules)
    offset = 0
    max_align = 1
    member_offsets = {}
    member_sizes = {}
    member_types = {}
    for name, type_name, size, align in members:
        offset = _align_up(offset, align)
        member_offsets[name] = offset
        member_sizes[name] = size
        member_types[name] = type_name
        offset += size
        if align > max_align:
            max_align = align

    # Final struct size is padded to struct alignment
    total_size = _align_up(offset, max_align)

    layout = StructLayout(
        kind="struct",
        name="S",
        size=total_size,
        align=max_align,
        member_offsets=member_offsets,
        member_sizes=member_sizes,
        member_types=member_types,
    )
    return layout


@st.composite
def small_struct_layout(draw, type_pool=ALL_SCALAR_TYPES):
    """Generate a struct layout with size ≤ 16 bytes from *type_pool*."""
    # Limit member count to keep size small
    num_members = draw(st.integers(min_value=1, max_value=4))
    # Prefer smaller types to stay within 16 bytes
    members = []
    for i in range(num_members):
        type_name, size, align = draw(st.sampled_from(type_pool))
        members.append((f"m{i}", type_name, size, align))

    offset = 0
    max_align = 1
    member_offsets = {}
    member_sizes = {}
    member_types = {}
    for name, type_name, size, align in members:
        offset = _align_up(offset, align)
        member_offsets[name] = offset
        member_sizes[name] = size
        member_types[name] = type_name
        offset += size
        if align > max_align:
            max_align = align

    total_size = _align_up(offset, max_align)
    assume(0 < total_size <= 16)

    return StructLayout(
        kind="struct", name="S", size=total_size, align=max_align,
        member_offsets=member_offsets, member_sizes=member_sizes,
        member_types=member_types,
    )


# Small integer types that fit easily within 16 bytes
SMALL_INTEGER_TYPES = [
    ("char", 1, 1),
    ("short", 2, 2),
    ("int", 4, 4),
]

SMALL_FLOAT_TYPES = [
    ("float", 4, 4),
]


@st.composite
def integer_only_layout(draw):
    """Generate a struct layout ≤ 16 bytes with only integer-type members."""
    return draw(small_struct_layout(type_pool=INTEGER_TYPES))


@st.composite
def float_only_layout(draw):
    """Generate a struct layout ≤ 16 bytes with only float/double members."""
    return draw(small_struct_layout(type_pool=FLOAT_TYPES))


@st.composite
def long_double_layout(draw):
    """Generate a struct layout that includes at least one long double member."""
    # Pick 0-3 normal members, then add a long double
    num_normal = draw(st.integers(min_value=0, max_value=3))
    members = []
    for i in range(num_normal):
        type_name, size, align = draw(st.sampled_from(ALL_SCALAR_TYPES))
        members.append((f"m{i}", type_name, size, align))

    # Insert long double at a random position
    ld_pos = draw(st.integers(min_value=0, max_value=len(members)))
    members.insert(ld_pos, (f"ld{ld_pos}", "long double", 16, 16))

    offset = 0
    max_align = 1
    member_offsets = {}
    member_sizes = {}
    member_types = {}
    for name, type_name, size, align in members:
        offset = _align_up(offset, align)
        member_offsets[name] = offset
        member_sizes[name] = size
        member_types[name] = type_name
        offset += size
        if align > max_align:
            max_align = align

    total_size = _align_up(offset, max_align)
    layout = StructLayout(
        kind="struct", name="S", size=total_size, align=max_align,
        member_offsets=member_offsets, member_sizes=member_sizes,
        member_types=member_types,
    )
    return layout


@st.composite
def large_struct_layout(draw):
    """Generate a struct layout with size > 16 bytes (no long double)."""
    # Use enough members to exceed 16 bytes
    num_members = draw(st.integers(min_value=3, max_value=8))
    members = []
    for i in range(num_members):
        type_name, size, align = draw(st.sampled_from(ALL_SCALAR_TYPES))
        members.append((f"m{i}", type_name, size, align))

    offset = 0
    max_align = 1
    member_offsets = {}
    member_sizes = {}
    member_types = {}
    for name, type_name, size, align in members:
        offset = _align_up(offset, align)
        member_offsets[name] = offset
        member_sizes[name] = size
        member_types[name] = type_name
        offset += size
        if align > max_align:
            max_align = align

    total_size = _align_up(offset, max_align)
    assume(total_size > 16)

    layout = StructLayout(
        kind="struct", name="S", size=total_size, align=max_align,
        member_offsets=member_offsets, member_sizes=member_sizes,
        member_types=member_types,
    )
    return layout


# ---------------------------------------------------------------------------
# Property tests
# ---------------------------------------------------------------------------

class TestStructClassifierProperties:
    """Property-based tests for StructClassifier invariants.

    **Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5**
    """

    @given(layout=large_struct_layout())
    @settings(max_examples=100)
    def test_large_structs_always_memory(self, layout):
        """Structs > 16 bytes always classify as MEMORY.

        **Validates: Requirements 2.2**
        """
        result = classify_struct("struct S", layout)
        assert result == [EightbyteClass.MEMORY], (
            f"Struct of size {layout.size} should be MEMORY, got {result}"
        )

    @given(layout=long_double_layout())
    @settings(max_examples=100)
    def test_long_double_members_always_memory(self, layout):
        """Structs with long double members always classify as MEMORY.

        **Validates: Requirements 2.4**
        """
        result = classify_struct("struct S", layout)
        assert result == [EightbyteClass.MEMORY], (
            f"Struct with long double member should be MEMORY, got {result}"
        )

    @given(layout=integer_only_layout())
    @settings(max_examples=100)
    def test_small_integer_only_all_eightbytes_integer(self, layout):
        """Structs ≤ 16 bytes with only integer members classify all eightbytes as INTEGER.

        **Validates: Requirements 2.1**
        """
        result = classify_struct("struct S", layout)
        assert all(c == EightbyteClass.INTEGER for c in result), (
            f"Integer-only struct should have all INTEGER eightbytes, got {result}"
        )

    @given(layout=float_only_layout())
    @settings(max_examples=100)
    def test_small_float_only_all_eightbytes_sse(self, layout):
        """Structs ≤ 16 bytes with only float/double members classify all eightbytes as SSE.

        **Validates: Requirements 2.4**
        """
        result = classify_struct("struct S", layout)
        assert all(c == EightbyteClass.SSE for c in result), (
            f"Float-only struct should have all SSE eightbytes, got {result}"
        )

    @given(layout=struct_layout_strategy())
    @settings(max_examples=200)
    def test_at_most_two_eightbytes_for_small_structs(self, layout):
        """classify_struct returns at most 2 eightbytes for structs ≤ 16 bytes.

        **Validates: Requirements 2.1, 2.4**
        """
        result = classify_struct("struct S", layout)
        if layout.size <= 16 and layout.size > 0:
            assert len(result) <= 2, (
                f"Struct of size {layout.size} should have ≤ 2 eightbytes, got {len(result)}"
            )

    @given(layout=struct_layout_strategy())
    @settings(max_examples=200)
    def test_get_struct_pass_mode_returns_valid_value(self, layout):
        """get_struct_pass_mode returns one of 'registers', 'stack', 'hidden_ptr'.

        **Validates: Requirements 2.1, 2.2, 2.5**
        """
        classification = classify_struct("struct S", layout)
        mode = get_struct_pass_mode(classification)
        assert mode in ("registers", "stack", "hidden_ptr"), (
            f"Invalid pass mode: {mode}"
        )

    @given(layout=struct_layout_strategy())
    @settings(max_examples=200)
    def test_memory_classification_implies_hidden_ptr(self, layout):
        """If any eightbyte is MEMORY, pass mode must be 'hidden_ptr'.

        **Validates: Requirements 2.2**
        """
        classification = classify_struct("struct S", layout)
        if any(c == EightbyteClass.MEMORY for c in classification):
            mode = get_struct_pass_mode(classification)
            assert mode == "hidden_ptr", (
                f"MEMORY classification should give hidden_ptr, got {mode}"
            )

    @given(
        a=st.sampled_from([EightbyteClass.NO_CLASS, EightbyteClass.INTEGER,
                           EightbyteClass.SSE, EightbyteClass.MEMORY]),
        b=st.sampled_from([EightbyteClass.NO_CLASS, EightbyteClass.INTEGER,
                           EightbyteClass.SSE, EightbyteClass.MEMORY]),
    )
    @settings(max_examples=100)
    def test_merge_rule_priority(self, a, b):
        """Merge rule: MEMORY > INTEGER > SSE > NO_CLASS is respected.

        **Validates: Requirements 2.1, 2.4**
        """
        merged = _merge_classes(a, b)

        # MEMORY dominates everything
        if a == EightbyteClass.MEMORY or b == EightbyteClass.MEMORY:
            assert merged == EightbyteClass.MEMORY

        # INTEGER dominates SSE and NO_CLASS
        elif a == EightbyteClass.INTEGER or b == EightbyteClass.INTEGER:
            assert merged == EightbyteClass.INTEGER

        # SSE dominates NO_CLASS
        elif a == EightbyteClass.SSE or b == EightbyteClass.SSE:
            assert merged == EightbyteClass.SSE

        # Both NO_CLASS
        else:
            assert merged == EightbyteClass.NO_CLASS

    @given(
        type_str=st.sampled_from([
            "char", "signed char", "unsigned char",
            "short", "unsigned short",
            "int", "unsigned int",
            "long", "unsigned long", "long long", "unsigned long long",
            "int*", "char*", "void*",
            "enum Color",
        ])
    )
    @settings(max_examples=100)
    def test_classify_field_integer_types(self, type_str):
        """All integer/pointer/enum types classify as INTEGER.

        **Validates: Requirements 2.1**
        """
        assert _classify_field(type_str) == EightbyteClass.INTEGER

    @given(type_str=st.sampled_from(["float", "double"]))
    @settings(max_examples=20)
    def test_classify_field_sse_types(self, type_str):
        """float and double classify as SSE.

        **Validates: Requirements 2.4**
        """
        assert _classify_field(type_str) == EightbyteClass.SSE

    @given(layout=struct_layout_strategy())
    @settings(max_examples=200)
    def test_classification_consistency_with_pass_mode(self, layout):
        """Classification and pass mode are always consistent:
        - MEMORY in classification → hidden_ptr
        - No MEMORY and non-empty → registers
        - Empty → stack

        **Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5**
        """
        classification = classify_struct("struct S", layout)
        mode = get_struct_pass_mode(classification)

        has_memory = any(c == EightbyteClass.MEMORY for c in classification)

        if not classification:
            assert mode == "stack"
        elif has_memory:
            assert mode == "hidden_ptr"
        else:
            assert mode == "registers"

    @given(layout=struct_layout_strategy())
    @settings(max_examples=200)
    def test_eightbyte_classes_are_valid(self, layout):
        """Every eightbyte class in the result is a valid EightbyteClass value.

        **Validates: Requirements 2.1, 2.4**
        """
        valid = {EightbyteClass.NO_CLASS, EightbyteClass.INTEGER,
                 EightbyteClass.SSE, EightbyteClass.MEMORY}
        classification = classify_struct("struct S", layout)
        for c in classification:
            assert c in valid, f"Invalid eightbyte class: {c}"
