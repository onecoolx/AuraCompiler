"""Property tests: integer promotion correctness (Property 3)."""
from hypothesis import given, strategies as st

from pycc.types import (
    IntegerType, EnumType, TypeKind,
    integer_promote, integer_rank, is_integer,
)

_narrow_types = st.builds(
    IntegerType,
    kind=st.sampled_from([TypeKind.CHAR, TypeKind.SHORT]),
    is_unsigned=st.booleans(),
)
_enum_types = st.builds(EnumType, kind=st.just(TypeKind.ENUM), tag=st.just("E"))
_promotable = st.one_of(_narrow_types, _enum_types)


@given(t=_promotable)
def test_promotion_yields_int_or_unsigned_int(t):
    result = integer_promote(t)
    assert result.kind == TypeKind.INT


@given(t=_promotable)
def test_promoted_rank_ge_int(t):
    result = integer_promote(t)
    assert integer_rank(result) >= integer_rank(IntegerType(kind=TypeKind.INT))


def test_int_not_promoted():
    t = IntegerType(kind=TypeKind.INT, is_unsigned=False)
    assert integer_promote(t) is t


def test_long_not_promoted():
    t = IntegerType(kind=TypeKind.LONG, is_unsigned=True)
    assert integer_promote(t) is t
