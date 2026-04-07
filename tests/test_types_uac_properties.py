"""Property tests: UAC result type correctness (Property 4)."""
from hypothesis import given, strategies as st

from pycc.types import (
    IntegerType, FloatType, TypeKind,
    usual_arithmetic_conversions, is_integer, is_floating, is_arithmetic,
)

_int_types = st.builds(
    IntegerType,
    kind=st.sampled_from([TypeKind.CHAR, TypeKind.SHORT, TypeKind.INT, TypeKind.LONG]),
    is_unsigned=st.booleans(),
)
_float_types = st.builds(
    FloatType,
    kind=st.sampled_from([TypeKind.FLOAT, TypeKind.DOUBLE]),
)
_arith_types = st.one_of(_int_types, _float_types)


@given(a=_arith_types, b=_arith_types)
def test_uac_result_is_arithmetic(a, b):
    result = usual_arithmetic_conversions(a, b)
    assert is_arithmetic(result)


@given(a=_arith_types, b=_arith_types)
def test_uac_double_wins(a, b):
    result = usual_arithmetic_conversions(a, b)
    if a.kind == TypeKind.DOUBLE or b.kind == TypeKind.DOUBLE:
        assert result.kind == TypeKind.DOUBLE


@given(a=_int_types, b=_int_types)
def test_uac_integers_yield_integer(a, b):
    result = usual_arithmetic_conversions(a, b)
    assert is_integer(result)


@given(a=_arith_types, b=_arith_types)
def test_uac_symmetric(a, b):
    r1 = usual_arithmetic_conversions(a, b)
    r2 = usual_arithmetic_conversions(b, a)
    assert r1.kind == r2.kind
    assert getattr(r1, 'is_unsigned', False) == getattr(r2, 'is_unsigned', False)
