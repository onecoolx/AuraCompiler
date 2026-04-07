"""Property tests: CType construction roundtrip (Property 1)."""
import pytest
from hypothesis import given, strategies as st

from pycc.types import (
    CType, IntegerType, FloatType, PointerType, EnumType, StructType,
    TypeKind, Qualifiers,
    ast_type_to_ctype, ctype_to_ir_type, _str_to_ctype,
    is_integer, type_sizeof,
)


_base_integer_kinds = [TypeKind.CHAR, TypeKind.SHORT, TypeKind.INT, TypeKind.LONG]

_integer_types = st.builds(
    IntegerType,
    kind=st.sampled_from(_base_integer_kinds),
    quals=st.just(Qualifiers()),
    is_unsigned=st.booleans(),
)

_float_types = st.builds(
    FloatType,
    kind=st.sampled_from([TypeKind.FLOAT, TypeKind.DOUBLE]),
    quals=st.just(Qualifiers()),
)

_simple_types = st.one_of(_integer_types, _float_types)


@given(ct=_integer_types)
def test_integer_roundtrip(ct):
    """IntegerType -> ir string -> CType should preserve kind and signedness."""
    s = ctype_to_ir_type(ct)
    ct2 = _str_to_ctype(s)
    assert ct2.kind == ct.kind
    assert getattr(ct2, 'is_unsigned', False) == ct.is_unsigned


@given(ct=_float_types)
def test_float_roundtrip(ct):
    s = ctype_to_ir_type(ct)
    ct2 = _str_to_ctype(s)
    assert ct2.kind == ct.kind


@given(ct=_simple_types)
def test_pointer_roundtrip(ct):
    """Wrapping in PointerType and roundtripping preserves pointee."""
    pt = PointerType(kind=TypeKind.POINTER, pointee=ct)
    s = ctype_to_ir_type(pt)
    ct2 = _str_to_ctype(s)
    assert ct2.kind == TypeKind.POINTER
    assert ct2.pointee.kind == ct.kind


@given(ct=_simple_types)
def test_sizeof_positive(ct):
    """All concrete types have positive sizeof."""
    assert type_sizeof(ct) > 0
