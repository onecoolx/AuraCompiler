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
