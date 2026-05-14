# Feature: remove-var-types
# Property-based tests for type classification helpers and type conversion roundtrips
#
# **Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 3.1, 3.4**

import hypothesis
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from pycc.types import (
    TypedSymbolTable,
    CType,
    IntegerType,
    FloatType,
    PointerType,
    ArrayType,
    StructType,
    FunctionTypeCType,
    TypeKind,
    Qualifiers,
    ctype_to_ir_type,
    _str_to_ctype,
    type_sizeof,
)


# ---------------------------------------------------------------------------
# Reuse CType generation strategies from test_sym_table_props.py
# ---------------------------------------------------------------------------

@st.composite
def integer_type_st(draw):
    kind = draw(st.sampled_from([TypeKind.CHAR, TypeKind.SHORT, TypeKind.INT, TypeKind.LONG]))
    return IntegerType(kind=kind, quals=Qualifiers(), is_unsigned=draw(st.booleans()))


@st.composite
def float_type_st(draw):
    kind = draw(st.sampled_from([TypeKind.FLOAT, TypeKind.DOUBLE]))
    return FloatType(kind=kind, quals=Qualifiers())


@st.composite
def struct_type_st(draw):
    kind = draw(st.sampled_from([TypeKind.STRUCT, TypeKind.UNION]))
    tag = draw(st.text(
        alphabet=st.characters(whitelist_categories=('Ll', 'Lu'), whitelist_characters='_'),
        min_size=1, max_size=8,
    ))
    return StructType(kind=kind, quals=Qualifiers(), tag=tag)


@st.composite
def pointer_type_st(draw, base=None):
    if base is None:
        base = draw(st.one_of(integer_type_st(), float_type_st(), struct_type_st()))
    return PointerType(kind=TypeKind.POINTER, quals=Qualifiers(), pointee=base)


@st.composite
def array_type_st(draw):
    elem = draw(st.one_of(integer_type_st(), float_type_st()))
    size = draw(st.integers(min_value=1, max_value=1024))
    return ArrayType(kind=TypeKind.ARRAY, quals=Qualifiers(), element=elem, size=size)


@st.composite
def function_pointer_type_st(draw):
    ret = draw(st.one_of(integer_type_st(), float_type_st()))
    n_params = draw(st.integers(min_value=0, max_value=4))
    params = [draw(st.one_of(integer_type_st(), float_type_st())) for _ in range(n_params)]
    fn = FunctionTypeCType(
        kind=TypeKind.FUNCTION, quals=Qualifiers(),
        return_type=ret, param_types=params,
        is_variadic=draw(st.booleans()),
    )
    return PointerType(kind=TypeKind.POINTER, quals=Qualifiers(), pointee=fn)


def ctype_st():
    """Strategy that generates any valid CType."""
    return st.one_of(
        integer_type_st(),
        float_type_st(),
        struct_type_st(),
        pointer_type_st(),
        array_type_st(),
        function_pointer_type_st(),
    )


def symbol_name_st():
    """Strategy that generates any valid symbol name."""
    return st.one_of(
        st.integers(min_value=0, max_value=9999).map(lambda i: f"%t{i}"),
        st.text(
            alphabet=st.characters(whitelist_categories=('Ll', 'Lu'), whitelist_characters='_'),
            min_size=1, max_size=10,
        ).map(lambda s: f"@{s}"),
    )


# ---------------------------------------------------------------------------
# Property 2: 类型分类辅助函数与 CType.kind 一致性
#
# For any symbol registered in TypedSymbolTable, the _is_unsigned_operand,
# _is_pointer_operand, _is_array_operand, _is_struct_operand, _is_float_operand
# helper functions should return values consistent with the CType's kind and
# attributes.
#
# **Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5**
# ---------------------------------------------------------------------------

class _MockIRGenerator:
    """Minimal mock of IRGenerator to test classification helpers in isolation.

    Only provides _sym_table and _var_types (empty) so the helpers use
    the CType-based path exclusively.
    """

    def __init__(self, sym_table):
        self._sym_table = sym_table
        self._var_types = {}
        self._sema_ctx = None

    # Import the actual helper methods from IRGenerator
    from pycc.ir import IRGenerator as _IR
    _is_unsigned_operand = _IR._is_unsigned_operand
    _is_pointer_operand = _IR._is_pointer_operand
    _is_array_operand = _IR._is_array_operand
    _is_struct_operand = _IR._is_struct_operand
    _is_float_operand = _IR._is_float_operand


# Feature: remove-var-types, Property 2: Type classification helpers consistency with CType.kind
@given(name=symbol_name_st(), ctype=ctype_st())
@settings(max_examples=100)
def test_property2_type_classification_consistency(name, ctype):
    """Property 2: 类型分类辅助函数与 CType.kind 一致性

    For any symbol registered in TypedSymbolTable, the classification helpers
    return values consistent with the CType's kind and attributes.

    **Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5**
    """
    table = TypedSymbolTable(sema_ctx=None)
    table.insert(name, ctype)

    gen = _MockIRGenerator(table)

    # _is_unsigned_operand: True iff IntegerType with is_unsigned=True
    expected_unsigned = isinstance(ctype, IntegerType) and ctype.is_unsigned
    assert gen._is_unsigned_operand(name) == expected_unsigned, (
        f"_is_unsigned_operand({name!r}) mismatch for {ctype}"
    )

    # _is_pointer_operand: True iff kind == POINTER
    expected_pointer = ctype.kind == TypeKind.POINTER
    assert gen._is_pointer_operand(name) == expected_pointer, (
        f"_is_pointer_operand({name!r}) mismatch for {ctype}"
    )

    # _is_array_operand: True iff kind == ARRAY
    expected_array = ctype.kind == TypeKind.ARRAY
    assert gen._is_array_operand(name) == expected_array, (
        f"_is_array_operand({name!r}) mismatch for {ctype}"
    )

    # _is_struct_operand: True iff kind in {STRUCT, UNION}
    expected_struct = ctype.kind in (TypeKind.STRUCT, TypeKind.UNION)
    assert gen._is_struct_operand(name) == expected_struct, (
        f"_is_struct_operand({name!r}) mismatch for {ctype}"
    )

    # _is_float_operand: True iff kind in {FLOAT, DOUBLE}
    expected_float = ctype.kind in (TypeKind.FLOAT, TypeKind.DOUBLE)
    assert gen._is_float_operand(name) == expected_float, (
        f"_is_float_operand({name!r}) mismatch for {ctype}"
    )


# ---------------------------------------------------------------------------
# Property 3: ctype_to_ir_type 往返一致性
#
# For any valid CType, _str_to_ctype(ctype_to_ir_type(ct)) should produce
# a CType semantically equivalent to the original (kind same, unsigned same,
# pointer depth same).
#
# **Validates: Requirements 2.6**
# ---------------------------------------------------------------------------

@st.composite
def _simple_pointer_type_st(draw):
    """Pointer to a simple scalar type (no nested pointers)."""
    base = draw(st.one_of(integer_type_st(), float_type_st()))
    return PointerType(kind=TypeKind.POINTER, quals=Qualifiers(), pointee=base)


def _roundtrip_ctype_st():
    """Strategy for types that survive the ctype_to_ir_type -> _str_to_ctype roundtrip.

    Excludes: arrays (ctype_to_ir_type returns element type only),
              function pointers (complex string representation),
              struct/union (tag-based, not roundtrippable without context).
    """
    return st.one_of(
        integer_type_st(),
        float_type_st(),
        _simple_pointer_type_st(),
    )


def _kinds_equivalent(original: CType, roundtripped: CType) -> bool:
    """Check semantic equivalence after roundtrip: kind, unsigned, pointer depth."""
    if original.kind != roundtripped.kind:
        return False
    if isinstance(original, IntegerType) and isinstance(roundtripped, IntegerType):
        return original.is_unsigned == roundtripped.is_unsigned
    if isinstance(original, PointerType) and isinstance(roundtripped, PointerType):
        if original.pointee is None and roundtripped.pointee is None:
            return True
        if original.pointee is None or roundtripped.pointee is None:
            return False
        return _kinds_equivalent(original.pointee, roundtripped.pointee)
    if isinstance(original, FloatType) and isinstance(roundtripped, FloatType):
        return original.kind == roundtripped.kind
    return True


# Feature: remove-var-types, Property 3: ctype_to_ir_type roundtrip consistency
@given(ctype=_roundtrip_ctype_st())
@settings(max_examples=100)
def test_property3_ctype_to_ir_type_roundtrip(ctype):
    """Property 3: ctype_to_ir_type 往返一致性

    For any valid CType, _str_to_ctype(ctype_to_ir_type(ct)) produces a CType
    semantically equivalent to the original (kind same, unsigned same, pointer
    depth same).

    **Validates: Requirements 2.6**
    """
    ir_str = ctype_to_ir_type(ctype)
    roundtripped = _str_to_ctype(ir_str)

    assert _kinds_equivalent(ctype, roundtripped), (
        f"Roundtrip mismatch:\n"
        f"  original:    {ctype}\n"
        f"  ir_string:   {ir_str!r}\n"
        f"  roundtripped: {roundtripped}"
    )


# ---------------------------------------------------------------------------
# Property 4: type_sizeof 与 LP64 ABI 一致性
#
# For any valid CType, type_sizeof(ct) returns the correct byte size per
# x86-64 SysV LP64 ABI.
#
# **Validates: Requirements 3.1, 3.4**
# ---------------------------------------------------------------------------

_LP64_SIZES = {
    TypeKind.CHAR: 1,
    TypeKind.SHORT: 2,
    TypeKind.INT: 4,
    TypeKind.LONG: 8,
    TypeKind.FLOAT: 4,
    TypeKind.DOUBLE: 8,
    TypeKind.POINTER: 8,
}


def _sizeof_ctype_st():
    """Strategy for types whose LP64 size is deterministic without layouts.

    Excludes struct/union (need layout info) and function pointers.
    """
    return st.one_of(
        integer_type_st(),
        float_type_st(),
        pointer_type_st(),
        array_type_st(),
    )


def _expected_sizeof(ct: CType) -> int:
    """Compute expected LP64 size for a CType."""
    if ct.kind == TypeKind.POINTER:
        return 8
    if ct.kind == TypeKind.ARRAY and isinstance(ct, ArrayType):
        if ct.element is not None and ct.size is not None:
            return _expected_sizeof(ct.element) * ct.size
        return 0
    return _LP64_SIZES.get(ct.kind, 0)


# Feature: remove-var-types, Property 4: type_sizeof LP64 ABI consistency
@given(ctype=_sizeof_ctype_st())
@settings(max_examples=100)
def test_property4_type_sizeof_lp64_abi(ctype):
    """Property 4: type_sizeof 与 LP64 ABI 一致性

    For any valid CType, type_sizeof(ct) returns the correct byte size per
    x86-64 SysV LP64 ABI (char=1, short=2, int=4, long=8, pointer=8,
    float=4, double=8, array=element_size*count).

    **Validates: Requirements 3.1, 3.4**
    """
    actual = type_sizeof(ctype)
    expected = _expected_sizeof(ctype)

    assert actual == expected, (
        f"type_sizeof mismatch for {ctype}:\n"
        f"  expected: {expected}\n"
        f"  actual:   {actual}"
    )
