# Feature: remove-var-types, Property 6: 回退一致性
# Property-based tests for transition period fallback consistency
#
# **Validates: Requirements 5.1, 5.3**
#
# During the transition period, symbols may exist in BOTH _var_types (string)
# and _sym_table (CType). This test verifies that helper functions return
# consistent results regardless of which source they consult.
# The helpers that still have _var_types fallback are: _is_pointer_operand,
# _is_array_operand, _is_struct_operand, _is_float_operand.
# _is_unsigned_operand has already been migrated (no _var_types fallback).

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
    TypeKind,
    Qualifiers,
    ctype_to_ir_type,
)


# ---------------------------------------------------------------------------
# Strategies: generate types that roundtrip correctly through
# ctype_to_ir_type -> string-based classification
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
def simple_pointer_type_st(draw):
    """Pointer to a simple scalar (roundtrips correctly)."""
    base = draw(st.one_of(integer_type_st(), float_type_st()))
    return PointerType(kind=TypeKind.POINTER, quals=Qualifiers(), pointee=base)


@st.composite
def struct_type_st(draw):
    kind = draw(st.sampled_from([TypeKind.STRUCT, TypeKind.UNION]))
    tag = draw(st.text(
        alphabet=st.characters(whitelist_categories=('Ll', 'Lu'), whitelist_characters='_'),
        min_size=1, max_size=8,
    ))
    return StructType(kind=kind, quals=Qualifiers(), tag=tag)


def roundtrippable_ctype_st():
    """Types that roundtrip correctly for classification consistency checks.

    Includes integers, floats, simple pointers, and struct/union.
    Excludes: arrays (ctype_to_ir_type drops size info, returns element type),
              function pointers (complex string format).
    """
    return st.one_of(
        integer_type_st(),
        float_type_st(),
        simple_pointer_type_st(),
        struct_type_st(),
    )


# ---------------------------------------------------------------------------
# Symbol name strategies
# ---------------------------------------------------------------------------

def symbol_name_st():
    """Generate valid symbol names for testing."""
    return st.one_of(
        st.integers(min_value=0, max_value=9999).map(lambda i: f"%t{i}"),
        st.text(
            alphabet=st.characters(whitelist_categories=('Ll', 'Lu'), whitelist_characters='_'),
            min_size=1, max_size=10,
        ).map(lambda s: f"@{s}"),
    )


# ---------------------------------------------------------------------------
# Mock IRGenerator with BOTH _sym_table and _var_types populated
# ---------------------------------------------------------------------------

class _DualSourceMock:
    """Mock IRGenerator with both _sym_table and _var_types populated.

    The helpers will use _sym_table (primary path). We independently compute
    what the _var_types string-parsing fallback would return and verify
    consistency.
    """

    def __init__(self, sym_table, var_types: dict):
        self._sym_table = sym_table
        self._var_types = var_types
        self._sema_ctx = None

    from pycc.ir import IRGenerator as _IR
    _is_unsigned_operand = _IR._is_unsigned_operand
    _is_pointer_operand = _IR._is_pointer_operand
    _is_array_operand = _IR._is_array_operand
    _is_struct_operand = _IR._is_struct_operand
    _is_float_operand = _IR._is_float_operand


# ---------------------------------------------------------------------------
# String-based classification (what _var_types fallback would compute)
# ---------------------------------------------------------------------------

def _str_is_pointer(ty: str) -> bool:
    """Replicate the _var_types fallback logic for pointer check."""
    return isinstance(ty, str) and ty.strip().endswith("*")


def _str_is_float(ty: str) -> bool:
    """Replicate the _var_types fallback logic for float check."""
    return isinstance(ty, str) and ty.strip() in ("float", "double")


def _str_is_struct(ty: str) -> bool:
    """Replicate the _var_types fallback logic for struct/union check."""
    return isinstance(ty, str) and (
        ty.strip().startswith("struct ") or ty.strip().startswith("union "))


def _str_is_array(ty: str) -> bool:
    """Replicate the _var_types fallback logic for array check."""
    return isinstance(ty, str) and ty.strip().startswith("array(")


# ---------------------------------------------------------------------------
# Property 6: 回退一致性（过渡期）
#
# For any symbol that exists in BOTH _var_types and _sym_table, the helper
# functions (using _sym_table as primary) should return results consistent
# with what the _var_types string-parsing fallback would produce.
#
# **Validates: Requirements 5.1, 5.3**
# ---------------------------------------------------------------------------

# Feature: remove-var-types, Property 6: 回退一致性
@given(name=symbol_name_st(), ctype=roundtrippable_ctype_st())
@settings(max_examples=100)
def test_property6_fallback_consistency(name, ctype):
    """Property 6: 回退一致性（过渡期）

    For any symbol that exists in BOTH _var_types (as type string) and
    _sym_table (as CType), the helper functions return results consistent
    with what the _var_types string-parsing fallback would independently
    compute from the type string.

    This ensures that during the dual-write transition period, there is no
    divergence between the two type information sources.

    **Validates: Requirements 5.1, 5.3**
    """
    # Convert CType to IR type string (what _var_types would store)
    ir_string = ctype_to_ir_type(ctype)

    # Set up _sym_table with the CType
    table = TypedSymbolTable(sema_ctx=None)
    table.insert(name, ctype)

    # Set up _var_types with the type string
    var_types = {name: ir_string}

    # Create mock with both sources populated
    mock = _DualSourceMock(table, var_types)

    # The helper uses _sym_table (primary). Verify it matches what
    # the _var_types string parsing would independently produce.

    # _is_pointer_operand consistency
    sym_result_ptr = mock._is_pointer_operand(name)
    str_result_ptr = _str_is_pointer(ir_string)
    assert sym_result_ptr == str_result_ptr, (
        f"_is_pointer_operand inconsistency for {name!r}:\n"
        f"  CType: {ctype}\n"
        f"  ir_string: {ir_string!r}\n"
        f"  _sym_table path says: {sym_result_ptr}\n"
        f"  _var_types parsing says: {str_result_ptr}"
    )

    # _is_float_operand consistency
    sym_result_float = mock._is_float_operand(name)
    str_result_float = _str_is_float(ir_string)
    assert sym_result_float == str_result_float, (
        f"_is_float_operand inconsistency for {name!r}:\n"
        f"  CType: {ctype}\n"
        f"  ir_string: {ir_string!r}\n"
        f"  _sym_table path says: {sym_result_float}\n"
        f"  _var_types parsing says: {str_result_float}"
    )

    # _is_struct_operand consistency
    sym_result_struct = mock._is_struct_operand(name)
    str_result_struct = _str_is_struct(ir_string)
    assert sym_result_struct == str_result_struct, (
        f"_is_struct_operand inconsistency for {name!r}:\n"
        f"  CType: {ctype}\n"
        f"  ir_string: {ir_string!r}\n"
        f"  _sym_table path says: {sym_result_struct}\n"
        f"  _var_types parsing says: {str_result_struct}"
    )

    # _is_array_operand consistency (non-array types should be False in both)
    sym_result_arr = mock._is_array_operand(name)
    str_result_arr = _str_is_array(ir_string)
    assert sym_result_arr == str_result_arr, (
        f"_is_array_operand inconsistency for {name!r}:\n"
        f"  CType: {ctype}\n"
        f"  ir_string: {ir_string!r}\n"
        f"  _sym_table path says: {sym_result_arr}\n"
        f"  _var_types parsing says: {str_result_arr}"
    )

    # _is_unsigned_operand consistency
    # Note: this helper no longer has _var_types fallback (migrated in 2.3),
    # but we still verify the _sym_table result matches what string parsing
    # would give, to ensure the CType and string representations agree.
    # A type string is "unsigned" only if it starts with "unsigned " AND is
    # not a pointer (doesn't end with "*"). E.g. "unsigned char *" is a
    # pointer, not an unsigned integer.
    sym_result_unsigned = mock._is_unsigned_operand(name)
    s = ir_string.strip() if isinstance(ir_string, str) else ""
    str_result_unsigned = (s.lower().startswith("unsigned ") and not s.endswith("*"))
    assert sym_result_unsigned == str_result_unsigned, (
        f"_is_unsigned_operand inconsistency for {name!r}:\n"
        f"  CType: {ctype}\n"
        f"  ir_string: {ir_string!r}\n"
        f"  _sym_table path says: {sym_result_unsigned}\n"
        f"  string parsing says: {str_result_unsigned}"
    )
