# Feature: remove-var-types
# Property-based tests for TypedSymbolTable
#
# **Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.5, 6.6**

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
)


# ---------------------------------------------------------------------------
# Strategies for generating random CType objects
# ---------------------------------------------------------------------------

@st.composite
def qualifiers_st(draw):
    return Qualifiers(
        const=draw(st.booleans()),
        volatile=draw(st.booleans()),
    )


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


# ---------------------------------------------------------------------------
# Strategies for generating symbol names
# ---------------------------------------------------------------------------

def temp_name_st():
    """Generate temporary variable names like %t0, %t1, ..."""
    return st.integers(min_value=0, max_value=9999).map(lambda i: f"%t{i}")


def local_name_st():
    """Generate local variable names like @x, @my_var."""
    return st.text(
        alphabet=st.characters(whitelist_categories=('Ll', 'Lu'), whitelist_characters='_'),
        min_size=1, max_size=10,
    ).map(lambda s: f"@{s}")


def global_name_st():
    """Generate global variable names (plain identifiers)."""
    return st.text(
        alphabet=st.characters(whitelist_categories=('Ll', 'Lu'), whitelist_characters='_'),
        min_size=1, max_size=10,
    ).map(lambda s: f"@g_{s}")


def symbol_name_st():
    """Strategy that generates any valid symbol name."""
    return st.one_of(temp_name_st(), local_name_st(), global_name_st())


# ---------------------------------------------------------------------------
# Property 1: TypedSymbolTable 插入-查询往返一致性
#
# For any symbol name (%t*, @*, global) and any valid CType, inserting it
# into TypedSymbolTable and then looking it up via lookup() should return
# a semantically equivalent CType.
#
# **Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.5**
# ---------------------------------------------------------------------------

def ctypes_semantically_equal(a: CType, b: CType) -> bool:
    """Check if two CTypes are semantically equivalent."""
    if a.kind != b.kind:
        return False
    if isinstance(a, IntegerType) and isinstance(b, IntegerType):
        return a.is_unsigned == b.is_unsigned
    if isinstance(a, FloatType) and isinstance(b, FloatType):
        return True
    if isinstance(a, PointerType) and isinstance(b, PointerType):
        if a.pointee is None and b.pointee is None:
            return True
        if a.pointee is None or b.pointee is None:
            return False
        return ctypes_semantically_equal(a.pointee, b.pointee)
    if isinstance(a, ArrayType) and isinstance(b, ArrayType):
        if a.size != b.size:
            return False
        if a.element is None and b.element is None:
            return True
        if a.element is None or b.element is None:
            return False
        return ctypes_semantically_equal(a.element, b.element)
    if isinstance(a, StructType) and isinstance(b, StructType):
        return a.tag == b.tag
    if isinstance(a, FunctionTypeCType) and isinstance(b, FunctionTypeCType):
        if not ctypes_semantically_equal(a.return_type, b.return_type):
            return False
        if len(a.param_types) != len(b.param_types):
            return False
        return all(ctypes_semantically_equal(p1, p2)
                   for p1, p2 in zip(a.param_types, b.param_types))
    return True


# Feature: remove-var-types, Property 1: TypedSymbolTable insert-lookup roundtrip consistency
@given(name=symbol_name_st(), ctype=ctype_st())
@settings(max_examples=100)
def test_property1_insert_lookup_roundtrip(name, ctype):
    """Property 1: TypedSymbolTable 插入-查询往返一致性

    For any symbol name and any valid CType, inserting into TypedSymbolTable
    and looking up via lookup() returns a semantically equivalent CType.

    **Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.5**
    """
    table = TypedSymbolTable(sema_ctx=None)
    table.insert(name, ctype)
    result = table.lookup(name)
    assert result is not None, f"lookup({name!r}) returned None after insert"
    assert ctypes_semantically_equal(ctype, result), (
        f"Mismatch: inserted {ctype}, got {result}"
    )


# Feature: remove-var-types, Property 1 (scoped variant): insert in function scope
@given(name=symbol_name_st(), ctype=ctype_st())
@settings(max_examples=100)
def test_property1_insert_lookup_in_scope(name, ctype):
    """Property 1 (scoped): Insert within a function scope is visible via lookup.

    **Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.5**
    """
    table = TypedSymbolTable(sema_ctx=None)
    table.push_scope()
    table.insert(name, ctype)
    result = table.lookup(name)
    assert result is not None, f"lookup({name!r}) returned None after scoped insert"
    assert ctypes_semantically_equal(ctype, result), (
        f"Mismatch in scope: inserted {ctype}, got {result}"
    )


# ---------------------------------------------------------------------------
# Property 5: activate_function 恢复作用域
#
# For any function name and a set of local symbols, after push_scope() ->
# multiple insert() -> pop_scope(func_name), calling activate_function(func_name)
# should make all previously inserted symbols queryable via lookup().
#
# **Validates: Requirements 3.6, 6.6**
# ---------------------------------------------------------------------------

@st.composite
def function_symbols_st(draw):
    """Generate a function name and a list of (symbol_name, ctype) pairs."""
    func_name = draw(st.text(
        alphabet=st.characters(whitelist_categories=('Ll', 'Lu'), whitelist_characters='_'),
        min_size=1, max_size=10,
    ))
    n_symbols = draw(st.integers(min_value=1, max_value=10))
    symbols = []
    used_names = set()
    for _ in range(n_symbols):
        name = draw(symbol_name_st())
        # Ensure unique names within this function
        assume(name not in used_names)
        used_names.add(name)
        ct = draw(ctype_st())
        symbols.append((name, ct))
    return func_name, symbols


# Feature: remove-var-types, Property 5: activate_function restores scope
@given(data=function_symbols_st())
@settings(max_examples=100)
def test_property5_activate_function_restores_scope(data):
    """Property 5: activate_function 恢复作用域

    For any function name and a set of local symbols, after push_scope() ->
    multiple insert() -> pop_scope(func_name), calling activate_function(func_name)
    should make all previously inserted symbols queryable via lookup().

    **Validates: Requirements 3.6, 6.6**
    """
    func_name, symbols = data
    table = TypedSymbolTable(sema_ctx=None)

    # Simulate IR generation: push scope, insert locals, pop scope
    table.push_scope()
    for name, ctype in symbols:
        table.insert(name, ctype)
    table.pop_scope(func_name=func_name)

    # After pop_scope, symbols should NOT be visible in active scopes
    # (they are archived). But _locals still holds the last popped scope.
    # The key property: activate_function restores them.

    # Simulate codegen: activate the function's locals
    table.activate_function(func_name)

    # All symbols should now be queryable
    for name, ctype in symbols:
        result = table.lookup(name)
        assert result is not None, (
            f"lookup({name!r}) returned None after activate_function({func_name!r})"
        )
        assert ctypes_semantically_equal(ctype, result), (
            f"Mismatch after activate: inserted {ctype}, got {result}"
        )


# Feature: remove-var-types, Property 5 (multi-function): multiple functions
@given(
    data1=function_symbols_st(),
    data2=function_symbols_st(),
)
@settings(max_examples=100)
def test_property5_activate_function_multiple_functions(data1, data2):
    """Property 5 (multi-function): activate_function correctly switches between functions.

    **Validates: Requirements 3.6, 6.6**
    """
    func1, symbols1 = data1
    func2, symbols2 = data2
    assume(func1 != func2)

    table = TypedSymbolTable(sema_ctx=None)

    # First function
    table.push_scope()
    for name, ctype in symbols1:
        table.insert(name, ctype)
    table.pop_scope(func_name=func1)

    # Second function
    table.push_scope()
    for name, ctype in symbols2:
        table.insert(name, ctype)
    table.pop_scope(func_name=func2)

    # Activate first function - its symbols should be visible
    table.activate_function(func1)
    for name, ctype in symbols1:
        result = table.lookup(name)
        assert result is not None, (
            f"lookup({name!r}) returned None after activate_function({func1!r})"
        )
        assert ctypes_semantically_equal(ctype, result)

    # Activate second function - its symbols should be visible
    table.activate_function(func2)
    for name, ctype in symbols2:
        result = table.lookup(name)
        assert result is not None, (
            f"lookup({name!r}) returned None after activate_function({func2!r})"
        )
        assert ctypes_semantically_equal(ctype, result)
