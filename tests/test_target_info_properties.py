"""Property-based tests for pycc.target.TargetInfo.

Uses hypothesis to verify correctness properties across all valid inputs.
"""

from hypothesis import given, strategies as st, settings
import pytest

from pycc.target import TargetInfo
from pycc.types import (
    CType, TypeKind, IntegerType, FloatType, PointerType,
    EnumType, ctype_to_ir_type,
)


# -- Shared data -------------------------------------------------------------

# All legal C89 scalar type name spellings and their expected LP64 sizes.
_ALL_SCALAR_NAMES = {
    "char": 1, "signed char": 1, "unsigned char": 1,
    "short": 2, "short int": 2, "signed short": 2,
    "signed short int": 2, "unsigned short": 2, "unsigned short int": 2,
    "int": 4, "signed int": 4, "unsigned int": 4, "signed": 4,
    "long": 8, "long int": 8, "signed long": 8,
    "signed long int": 8, "unsigned long": 8, "unsigned long int": 8,
    "float": 4, "double": 8, "long double": 16,
}

_SCALAR_NAMES_LIST = list(_ALL_SCALAR_NAMES.keys())

_ti = TargetInfo.lp64()


# -- Strategies --------------------------------------------------------------

scalar_name_strategy = st.sampled_from(_SCALAR_NAMES_LIST)

# Strategy for scalar CType objects covering all TypeKind scalars.
_SCALAR_CTYPE_POOL = [
    IntegerType(kind=TypeKind.CHAR, is_unsigned=False),
    IntegerType(kind=TypeKind.CHAR, is_unsigned=True),
    IntegerType(kind=TypeKind.SHORT, is_unsigned=False),
    IntegerType(kind=TypeKind.SHORT, is_unsigned=True),
    IntegerType(kind=TypeKind.INT, is_unsigned=False),
    IntegerType(kind=TypeKind.INT, is_unsigned=True),
    IntegerType(kind=TypeKind.LONG, is_unsigned=False),
    IntegerType(kind=TypeKind.LONG, is_unsigned=True),
    FloatType(kind=TypeKind.FLOAT),
    FloatType(kind=TypeKind.DOUBLE),
    PointerType(kind=TypeKind.POINTER, pointee=IntegerType(kind=TypeKind.INT)),
    EnumType(kind=TypeKind.ENUM, tag="test_enum"),
]

scalar_ctype_strategy = st.sampled_from(_SCALAR_CTYPE_POOL)


# -- Property 1: String type name sizeof/alignof consistency ----------------
# **Validates: Requirements 1.1, 1.2, 2.2, 2.3**
#
# For any legal C89 scalar type name string (including all equivalent
# spelling forms), TargetInfo.lp64().sizeof(name) and alignof(name) return
# values consistent with the LP64 data model, and for scalar types sizeof
# and alignof return the same value.


@settings(max_examples=200)
@given(name=scalar_name_strategy)
def test_property1_sizeof_matches_lp64_spec(name):
    """sizeof returns the LP64-specified value for every scalar spelling."""
    expected = _ALL_SCALAR_NAMES[name]
    assert _ti.sizeof(name) == expected


@settings(max_examples=200)
@given(name=scalar_name_strategy)
def test_property1_alignof_matches_lp64_spec(name):
    """alignof returns the LP64-specified value for every scalar spelling."""
    expected = _ALL_SCALAR_NAMES[name]
    assert _ti.alignof(name) == expected


@settings(max_examples=200)
@given(name=scalar_name_strategy)
def test_property1_sizeof_equals_alignof_for_scalars(name):
    """For LP64 scalar types, sizeof and alignof are always equal."""
    assert _ti.sizeof(name) == _ti.alignof(name)


# -- Property 2: CType sizeof_ctype/alignof_ctype consistency ---------------
# **Validates: Requirements 1.3, 1.4, 6.2**
#
# For any CType object constructed from a scalar TypeKind,
# sizeof_ctype(ct) == sizeof(ctype_to_ir_type(ct)), i.e. the CType
# interface and string interface produce equivalent results.


@settings(max_examples=200)
@given(ct=scalar_ctype_strategy)
def test_property2_sizeof_ctype_matches_string_sizeof(ct):
    """sizeof_ctype(ct) equals sizeof(ctype_to_ir_type(ct))."""
    ir_name = ctype_to_ir_type(ct)
    assert _ti.sizeof_ctype(ct) == _ti.sizeof(ir_name)


@settings(max_examples=200)
@given(ct=scalar_ctype_strategy)
def test_property2_alignof_ctype_matches_string_alignof(ct):
    """alignof_ctype(ct) equals alignof(ctype_to_ir_type(ct))."""
    ir_name = ctype_to_ir_type(ct)
    assert _ti.alignof_ctype(ct) == _ti.alignof(ir_name)


# -- Property 4: Struct layout computation equivalence ----------------------
# **Validates: Requirements 5.3, 7.2**
#
# For any struct with scalar members, the layout computed using TargetInfo
# should produce the same offsets, sizes, and total size as the old
# hardcoded size_align logic.

from pycc.ast_nodes import Type, Declaration

# The old hardcoded size_align logic (copied verbatim from pre-refactor code)
_OLD_SCALAR_MAP = {
    "char": (1, 1), "unsigned char": (1, 1), "signed char": (1, 1),
    "short": (2, 2), "short int": (2, 2), "unsigned short": (2, 2),
    "unsigned short int": (2, 2), "signed short": (2, 2), "signed short int": (2, 2),
    "int": (4, 4), "unsigned int": (4, 4), "signed int": (4, 4),
    "long": (8, 8), "long int": (8, 8), "unsigned long": (8, 8),
    "unsigned long int": (8, 8), "signed long": (8, 8), "signed long int": (8, 8),
    "float": (4, 4), "double": (8, 8), "long double": (16, 16),
}


def _old_size_align(ty):
    """Replicate the old hardcoded size_align logic exactly."""
    if ty.is_pointer:
        return 8, 8
    b = ty.base.strip() if isinstance(ty.base, str) else ""
    if b in {"char", "unsigned char", "signed char"}:
        return 1, 1
    if b in {"short", "short int", "unsigned short", "unsigned short int",
             "signed short", "signed short int"}:
        return 2, 2
    if b in {"int", "unsigned int", "signed int"} or b.startswith("enum "):
        return 4, 4
    if b in {"long", "long int", "unsigned long", "unsigned long int",
             "signed long", "signed long int"}:
        return 8, 8
    if b == "float":
        return 4, 4
    if b == "double":
        return 8, 8
    if b == "long double":
        return 16, 16
    return 8, 8


def _new_size_align(ty):
    """Use TargetInfo to compute size and alignment."""
    if ty.is_pointer:
        return _ti.pointer_size, _ti.pointer_size
    b = ty.base.strip() if isinstance(ty.base, str) else ""
    s = _ti.sizeof(b)
    a = _ti.alignof(b)
    return s, a


def _compute_layout_generic(members, size_align_fn):
    """Compute struct layout using a given size_align function.

    Mirrors the non-bitfield path of SemanticAnalyzer._compute_layout.
    """
    offsets = {}
    sizes = {}
    off = 0
    max_align = 1

    for m in members:
        sz, al = size_align_fn(m.type)
        arr_size = getattr(m, 'array_size', None)
        if arr_size is not None:
            sz = sz * int(arr_size)
        if sz >= 8:
            al = max(al, 8)
        max_align = max(max_align, al)
        if off % al != 0:
            off += (al - (off % al))
        offsets[m.name] = off
        sizes[m.name] = sz
        off += sz

    total = off
    if total % max_align != 0:
        total += (max_align - (total % max_align))
    return offsets, sizes, total


# Scalar types suitable for struct members (no enum prefix needed for simplicity)
_MEMBER_TYPES = [
    "char", "unsigned char", "short", "int", "unsigned int",
    "long", "unsigned long", "float", "double", "long double",
]

# Strategy: generate a list of 1-8 struct members with random scalar types
_member_strategy = st.lists(
    st.tuples(
        st.sampled_from(_MEMBER_TYPES),
        st.booleans(),  # is_pointer
        st.one_of(st.none(), st.integers(min_value=1, max_value=16)),  # array_size
    ),
    min_size=1,
    max_size=8,
)


def _build_members(member_specs):
    """Build Declaration list from generated specs."""
    members = []
    for i, (type_name, is_ptr, arr_sz) in enumerate(member_specs):
        ty = Type(base=type_name, is_pointer=is_ptr, line=0, column=0)
        decl = Declaration(name=f"m{i}", type=ty, array_size=arr_sz, line=0, column=0)
        members.append(decl)
    return members


@settings(max_examples=200)
@given(specs=_member_strategy)
def test_property4_layout_offsets_match(specs):
    """Struct member offsets computed via TargetInfo match old hardcoded logic."""
    members = _build_members(specs)
    old_offsets, _, _ = _compute_layout_generic(members, _old_size_align)
    new_offsets, _, _ = _compute_layout_generic(members, _new_size_align)
    assert old_offsets == new_offsets


@settings(max_examples=200)
@given(specs=_member_strategy)
def test_property4_layout_sizes_match(specs):
    """Struct member sizes computed via TargetInfo match old hardcoded logic."""
    members = _build_members(specs)
    _, old_sizes, _ = _compute_layout_generic(members, _old_size_align)
    _, new_sizes, _ = _compute_layout_generic(members, _new_size_align)
    assert old_sizes == new_sizes


@settings(max_examples=200)
@given(specs=_member_strategy)
def test_property4_layout_total_size_match(specs):
    """Struct total size computed via TargetInfo matches old hardcoded logic."""
    members = _build_members(specs)
    _, _, old_total = _compute_layout_generic(members, _old_size_align)
    _, _, new_total = _compute_layout_generic(members, _new_size_align)
    assert old_total == new_total
