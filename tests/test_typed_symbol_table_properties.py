"""Property-based tests for TypedSymbolTable.

**Feature: ir-type-annotations, Property 2: Typedef 解析产生完全解析的 CType**
**Validates: Requirements 1.2, 2.2, 5.2, 9.1**

Property: For any typedef chain (including multi-level nesting), after inserting
a typedef name into TypedSymbolTable and querying it, the returned CType should
not contain any unresolved typedef references — CType.kind should be a concrete
type (INT, FLOAT, STRUCT, etc.), not a typedef name string residue.
"""
import pytest
from unittest.mock import MagicMock

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from pycc.types import (
    TypedSymbolTable,
    CType, IntegerType, FloatType, PointerType, ArrayType,
    StructType, EnumType,
    TypeKind, Qualifiers,
)
from pycc.ast_nodes import Type


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ty(base, **kwargs):
    """Create an ast_nodes.Type with dummy line/column."""
    return Type(line=0, column=0, base=base, **kwargs)


def _make_sema_ctx(typedefs):
    """Create a minimal mock SemanticContext."""
    ctx = MagicMock()
    ctx.typedefs = typedefs
    ctx.layouts = {}
    return ctx


# The set of concrete base types that are terminal (not typedef names).
_CONCRETE_BASES = [
    "int", "char", "short", "long", "float", "double", "void",
    "unsigned int", "unsigned char", "unsigned short", "unsigned long",
    "signed int", "signed char",
    "struct my_s", "union my_u", "enum my_e",
]

# Concrete TypeKinds that a fully-resolved CType should have.
_CONCRETE_KINDS = {
    TypeKind.VOID, TypeKind.CHAR, TypeKind.SHORT, TypeKind.INT,
    TypeKind.LONG, TypeKind.FLOAT, TypeKind.DOUBLE,
    TypeKind.POINTER, TypeKind.ARRAY,
    TypeKind.STRUCT, TypeKind.UNION, TypeKind.ENUM,
}


def _ctype_is_fully_resolved(ct, typedef_names):
    """Check that a CType contains no unresolved typedef references.

    A CType is fully resolved if:
    - Its kind is a concrete TypeKind (not a typedef name residue)
    - For StructType/EnumType, the tag is NOT one of the typedef names
      (it should have been resolved to the underlying struct/enum tag)
    - For PointerType, the pointee is also fully resolved
    - For ArrayType, the element is also fully resolved
    """
    if ct is None:
        return True
    if ct.kind not in _CONCRETE_KINDS:
        return False
    if isinstance(ct, StructType) and ct.tag in typedef_names:
        return False
    if isinstance(ct, EnumType) and ct.tag in typedef_names:
        return False
    if isinstance(ct, PointerType) and ct.pointee is not None:
        return _ctype_is_fully_resolved(ct.pointee, typedef_names)
    if isinstance(ct, ArrayType) and ct.element is not None:
        return _ctype_is_fully_resolved(ct.element, typedef_names)
    return True


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

# Strategy for generating typedef chain names like td_0, td_1, ...
_typedef_name = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz", min_size=2, max_size=6
).map(lambda s: "td_" + s)

# Strategy for a concrete base type string
_concrete_base = st.sampled_from(_CONCRETE_BASES)


@st.composite
def typedef_chain(draw):
    """Generate a typedef chain of depth 1..5 ending at a concrete type.

    Returns (typedefs_dict, leaf_typedef_name, concrete_base).
    Example for depth=3:
      td_abc -> td_def -> td_ghi -> "int"
      typedefs = {"td_abc": Type(base="td_def"),
                  "td_def": Type(base="td_ghi"),
                  "td_ghi": Type(base="int")}
      leaf = "td_abc"
      concrete = "int"
    """
    depth = draw(st.integers(min_value=1, max_value=5))
    concrete = draw(_concrete_base)

    # Generate unique typedef names
    names = []
    seen = set()
    for _ in range(depth):
        name = draw(_typedef_name.filter(lambda n, s=seen: n not in s))
        seen.add(name)
        names.append(name)

    # Build the chain: names[0] -> names[1] -> ... -> names[-1] -> concrete
    typedefs = {}
    for i, name in enumerate(names):
        if i < len(names) - 1:
            # Points to next typedef in chain
            target = names[i + 1]
        else:
            # Terminal: points to concrete type
            target = concrete

        # Determine if target needs pointer or unsigned flags
        is_ptr = False
        ptr_level = 0
        is_unsigned = "unsigned" in target
        base = target.replace("unsigned ", "").strip()
        if not base:
            base = "int"

        typedefs[name] = _ty(base, is_unsigned=is_unsigned)

    return typedefs, names[0], concrete


@st.composite
def typedef_chain_with_pointer(draw):
    """Generate a typedef chain where the leaf is a pointer to a concrete type.

    Returns (typedefs_dict, leaf_typedef_name).
    Example: td_abc -> td_def -> int*
    """
    depth = draw(st.integers(min_value=1, max_value=4))
    concrete = draw(_concrete_base)
    ptr_level = draw(st.integers(min_value=1, max_value=3))

    names = []
    seen = set()
    for _ in range(depth):
        name = draw(_typedef_name.filter(lambda n, s=seen: n not in s))
        seen.add(name)
        names.append(name)

    typedefs = {}
    for i, name in enumerate(names):
        if i < len(names) - 1:
            target = names[i + 1]
            typedefs[name] = _ty(target)
        else:
            # Terminal: pointer to concrete type
            is_unsigned = "unsigned" in concrete
            base = concrete.replace("unsigned ", "").strip() or "int"
            typedefs[name] = _ty(
                base, is_pointer=True, pointer_level=ptr_level,
                is_unsigned=is_unsigned,
            )

    return typedefs, names[0]


# ---------------------------------------------------------------------------
# Property tests
# ---------------------------------------------------------------------------

class TestProperty2TypedefResolution:
    """Property 2: Typedef 解析产生完全解析的 CType

    **Feature: ir-type-annotations, Property 2: Typedef 解析产生完全解析的 CType**
    **Validates: Requirements 1.2, 2.2, 5.2, 9.1**
    """

    @given(data=typedef_chain())
    @settings(max_examples=150)
    def test_typedef_chain_resolves_to_concrete_kind(self, data):
        """Any typedef chain resolves to a CType with a concrete TypeKind."""
        typedefs, leaf_name, concrete_base = data
        sema = _make_sema_ctx(typedefs)
        st_table = TypedSymbolTable(sema_ctx=sema)

        # Insert the leaf typedef as a StructType with tag=leaf_name
        # (this is how unresolved typedef names appear in CType before resolution)
        ct_input = StructType(kind=TypeKind.STRUCT, tag=leaf_name)
        st_table.insert("@var", ct_input)

        result = st_table.lookup("@var")
        assert result is not None, "Symbol should be found after insert"
        assert result.kind in _CONCRETE_KINDS, (
            f"Resolved CType kind {result.kind} is not concrete. "
            f"Chain: {leaf_name} -> ... -> {concrete_base}"
        )

    @given(data=typedef_chain())
    @settings(max_examples=150)
    def test_typedef_chain_no_typedef_residue(self, data):
        """Resolved CType should not contain any typedef name as a tag."""
        typedefs, leaf_name, concrete_base = data
        typedef_names = set(typedefs.keys())
        sema = _make_sema_ctx(typedefs)
        st_table = TypedSymbolTable(sema_ctx=sema)

        ct_input = StructType(kind=TypeKind.STRUCT, tag=leaf_name)
        st_table.insert("@var", ct_input)

        result = st_table.lookup("@var")
        assert result is not None
        assert _ctype_is_fully_resolved(result, typedef_names), (
            f"CType still contains typedef residue. "
            f"Result: kind={result.kind}, "
            f"tag={getattr(result, 'tag', None)}. "
            f"Typedef names: {typedef_names}"
        )

    @given(data=typedef_chain_with_pointer())
    @settings(max_examples=150)
    def test_pointer_typedef_chain_resolves_fully(self, data):
        """Pointer typedef chains resolve pointee to concrete type."""
        typedefs, leaf_name = data
        typedef_names = set(typedefs.keys())
        sema = _make_sema_ctx(typedefs)
        st_table = TypedSymbolTable(sema_ctx=sema)

        ct_input = StructType(kind=TypeKind.STRUCT, tag=leaf_name)
        st_table.insert("@ptr_var", ct_input)

        result = st_table.lookup("@ptr_var")
        assert result is not None
        assert _ctype_is_fully_resolved(result, typedef_names), (
            f"Pointer typedef chain not fully resolved. "
            f"Result kind={result.kind}, "
            f"pointee={getattr(result, 'pointee', None)}"
        )

    @given(data=typedef_chain())
    @settings(max_examples=100)
    def test_direct_resolve_typedef_name_matches_insert(self, data):
        """_resolve_typedef_name and insert+lookup produce equivalent results."""
        typedefs, leaf_name, concrete_base = data
        sema = _make_sema_ctx(typedefs)
        st_table = TypedSymbolTable(sema_ctx=sema)

        # Direct resolution via internal method
        direct = st_table._resolve_typedef_name(leaf_name, set())
        assert direct is not None, (
            f"_resolve_typedef_name returned None for known typedef {leaf_name}"
        )

        # Via insert + lookup
        ct_input = StructType(kind=TypeKind.STRUCT, tag=leaf_name)
        st_table.insert("@check", ct_input)
        via_insert = st_table.lookup("@check")

        # Both should have the same concrete kind
        assert direct.kind == via_insert.kind, (
            f"Direct resolve kind={direct.kind} != "
            f"insert+lookup kind={via_insert.kind}"
        )


# ---------------------------------------------------------------------------
# Strategies for Property 3
# ---------------------------------------------------------------------------

# Strategy for generating IR symbol names (locals @name, temps %tN)
_symbol_name = st.one_of(
    st.text(alphabet="abcdefghijklmnopqrstuvwxyz_", min_size=1, max_size=8)
    .map(lambda s: "@" + s),
    st.integers(min_value=0, max_value=9999).map(lambda n: f"%t{n}"),
)

# Strategy for generating distinct CType instances
_ctype_strategy = st.sampled_from([
    IntegerType(kind=TypeKind.INT, is_unsigned=False),
    IntegerType(kind=TypeKind.INT, is_unsigned=True),
    IntegerType(kind=TypeKind.CHAR, is_unsigned=False),
    IntegerType(kind=TypeKind.CHAR, is_unsigned=True),
    IntegerType(kind=TypeKind.SHORT, is_unsigned=False),
    IntegerType(kind=TypeKind.LONG, is_unsigned=False),
    IntegerType(kind=TypeKind.LONG, is_unsigned=True),
    FloatType(kind=TypeKind.FLOAT),
    FloatType(kind=TypeKind.DOUBLE),
    PointerType(kind=TypeKind.POINTER, pointee=IntegerType(kind=TypeKind.INT)),
    PointerType(kind=TypeKind.POINTER, pointee=IntegerType(kind=TypeKind.CHAR)),
    PointerType(kind=TypeKind.POINTER, pointee=CType(kind=TypeKind.VOID)),
    StructType(kind=TypeKind.STRUCT, tag="my_struct"),
    StructType(kind=TypeKind.STRUCT, tag="other_struct"),
    ArrayType(kind=TypeKind.ARRAY, element=IntegerType(kind=TypeKind.INT), size=10),
    EnumType(kind=TypeKind.ENUM, tag="my_enum"),
])


@st.composite
def global_and_local_types(draw):
    """Generate a symbol name with two distinct CTypes for global and local scope.

    Returns (symbol_name, global_ctype, local_ctype) where global_ctype != local_ctype.
    """
    name = draw(_symbol_name)
    global_ct = draw(_ctype_strategy)
    local_ct = draw(_ctype_strategy)
    # Ensure the two types are distinguishable
    assume(global_ct.kind != local_ct.kind
           or type(global_ct) != type(local_ct)
           or getattr(global_ct, 'is_unsigned', None) != getattr(local_ct, 'is_unsigned', None)
           or getattr(global_ct, 'tag', None) != getattr(local_ct, 'tag', None)
           or getattr(global_ct, 'pointee', None) != getattr(local_ct, 'pointee', None))
    return name, global_ct, local_ct


# ---------------------------------------------------------------------------
# Property 3 tests
# ---------------------------------------------------------------------------

class TestProperty3ScopeLookupPriority:
    """Property 3: 作用域查找优先返回局部符号

    **Feature: ir-type-annotations, Property 3: 作用域查找优先返回局部符号**
    **Validates: Requirements 2.4**

    For any symbol name, if that name exists in both the global scope and the
    current function local scope, TypedSymbolTable.lookup should return the
    CType from the local scope, not the global scope.
    """

    @given(data=global_and_local_types())
    @settings(max_examples=150)
    def test_local_shadows_global(self, data):
        """lookup returns local CType when same name exists in both scopes."""
        name, global_ct, local_ct = data
        table = TypedSymbolTable()

        # Insert into global scope (no scope pushed)
        table.insert(name, global_ct)
        # Push a function scope and insert the same name with a different type
        table.push_scope()
        table.insert(name, local_ct)

        result = table.lookup(name)
        assert result is not None, "Symbol should be found"
        assert result is local_ct, (
            f"lookup should return local CType {local_ct} "
            f"but got {result} (global was {global_ct})"
        )

        table.pop_scope()

    @given(data=global_and_local_types())
    @settings(max_examples=150)
    def test_global_visible_after_scope_pop(self, data):
        """After popping local scope, lookup returns the global CType."""
        name, global_ct, local_ct = data
        table = TypedSymbolTable()

        table.insert(name, global_ct)
        table.push_scope()
        table.insert(name, local_ct)

        # While in scope, local shadows global
        assert table.lookup(name) is local_ct

        # After pop, global is visible again
        table.pop_scope()
        result = table.lookup(name)
        assert result is not None, "Global symbol should still exist after pop"
        assert result is global_ct, (
            f"After pop_scope, lookup should return global CType {global_ct} "
            f"but got {result}"
        )

    @given(name=_symbol_name, ct=_ctype_strategy)
    @settings(max_examples=100)
    def test_global_only_when_no_local(self, name, ct):
        """lookup returns global CType when no local scope shadows it."""
        table = TypedSymbolTable()
        table.insert(name, ct)

        # No scope pushed — lookup should find global
        assert table.lookup(name) is ct

        # Push an empty scope — global still visible
        table.push_scope()
        assert table.lookup(name) is ct
        table.pop_scope()

    @given(name=_symbol_name, ct=_ctype_strategy)
    @settings(max_examples=100)
    def test_local_only_no_global(self, name, ct):
        """lookup returns local CType even when no global entry exists."""
        table = TypedSymbolTable()
        table.push_scope()
        table.insert(name, ct)

        result = table.lookup(name)
        assert result is ct, (
            f"lookup should return local CType {ct} but got {result}"
        )
        table.pop_scope()

    @given(name=_symbol_name)
    @settings(max_examples=100)
    def test_lookup_returns_none_when_absent(self, name):
        """lookup returns None for a symbol that was never inserted."""
        table = TypedSymbolTable()
        assert table.lookup(name) is None

        table.push_scope()
        assert table.lookup(name) is None
        table.pop_scope()
