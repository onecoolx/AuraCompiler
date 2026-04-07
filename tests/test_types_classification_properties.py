"""Property tests: type classification function consistency (Property 2)."""
import pytest
from hypothesis import given, strategies as st

from pycc.types import (
    CType, IntegerType, FloatType, PointerType, ArrayType,
    FunctionTypeCType, StructType, EnumType,
    TypeKind, Qualifiers,
    is_integer, is_floating, is_arithmetic, is_scalar,
    is_object, is_function, is_incomplete, is_modifiable_lvalue,
)

# Strategy: generate arbitrary CType instances
_quals = st.builds(Qualifiers, const=st.booleans(), volatile=st.booleans())

_integer_types = st.builds(
    IntegerType,
    kind=st.sampled_from([TypeKind.CHAR, TypeKind.SHORT, TypeKind.INT, TypeKind.LONG]),
    quals=_quals,
    is_unsigned=st.booleans(),
)
_enum_types = st.builds(EnumType, kind=st.just(TypeKind.ENUM), quals=_quals, tag=st.just("E"))
_float_types = st.builds(
    FloatType,
    kind=st.sampled_from([TypeKind.FLOAT, TypeKind.DOUBLE]),
    quals=_quals,
)
_pointer_types = st.builds(
    PointerType,
    kind=st.just(TypeKind.POINTER),
    quals=_quals,
    pointee=st.just(IntegerType(kind=TypeKind.INT)),
)
_void_types = st.builds(CType, kind=st.just(TypeKind.VOID), quals=_quals)
_func_types = st.builds(
    FunctionTypeCType,
    kind=st.just(TypeKind.FUNCTION),
    quals=_quals,
)
_all_types = st.one_of(
    _integer_types, _enum_types, _float_types, _pointer_types,
    _void_types, _func_types,
)


@given(t=_all_types)
def test_scalar_iff_arithmetic_or_pointer(t):
    assert is_scalar(t) == (is_arithmetic(t) or t.kind == TypeKind.POINTER)


@given(t=_all_types)
def test_arithmetic_iff_integer_or_floating(t):
    assert is_arithmetic(t) == (is_integer(t) or is_floating(t))


@given(t=_all_types)
def test_integer_and_floating_mutually_exclusive(t):
    assert not (is_integer(t) and is_floating(t))


@given(t=_all_types)
def test_function_implies_not_object(t):
    if is_function(t):
        assert not is_object(t)
