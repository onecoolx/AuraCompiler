"""Property-based tests for IRGenerator._resolve_full_type method.

**Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5**

Property 1: Type Resolution Correctness
For any typedef chain (A -> B -> C -> base type), _resolve_full_type should
correctly classify the final type's kind (scalar/pointer/array/struct/union),
and the resolved name should be the base type at the end of the chain.
"""
import pytest
from dataclasses import dataclass, field
from typing import Dict, Optional

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from pycc.ir import IRGenerator, ResolvedType
from pycc.ast_nodes import Type, Declaration


# ---------------------------------------------------------------------------
# Helpers (reused from test_resolve_full_type.py)
# ---------------------------------------------------------------------------

def _T(**kwargs):
    """Shorthand to create a Type node with dummy line/column."""
    return Type(line=0, column=0, **kwargs)


@dataclass
class MockStructLayout:
    kind: str
    name: str
    size: int
    align: int
    member_offsets: Dict[str, int]
    member_sizes: Dict[str, int]
    member_types: Optional[Dict[str, str]] = None


@dataclass
class MockSemaCtx:
    typedefs: Dict[str, Type] = field(default_factory=dict)
    layouts: Dict[str, MockStructLayout] = field(default_factory=dict)


def _make_irgen(sema_ctx=None):
    """Create an IRGenerator with optional sema_ctx."""
    gen = IRGenerator()
    gen._sema_ctx = sema_ctx
    return gen


def _make_decl(name, base, is_pointer=False, pointer_level=0,
               array_size=None, array_dims=None, is_array=False,
               array_dimensions=None):
    """Create a Declaration AST node for testing."""
    ty = Type(line=0, column=0, base=base, is_pointer=is_pointer,
              pointer_level=pointer_level, is_array=is_array,
              array_dimensions=array_dimensions)
    decl = Declaration(line=0, column=0, name=name, type=ty,
                       array_size=array_size, array_dims=array_dims)
    return decl


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Known scalar types with their expected (size, is_float) properties
SCALAR_TYPES = {
    "char": (1, False),
    "signed char": (1, False),
    "unsigned char": (1, False),
    "short": (2, False),
    "unsigned short": (2, False),
    "int": (4, False),
    "unsigned int": (4, False),
    "long": (8, False),
    "unsigned long": (8, False),
    "float": (4, True),
    "double": (8, True),
    "long double": (16, True),
    "_Bool": (1, False),
}

# Strategy for scalar type names
scalar_type_st = st.sampled_from(list(SCALAR_TYPES.keys()))

# Strategy for typedef chain names (unique identifiers that won't collide)
typedef_name_st = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz", min_size=3, max_size=8
).map(lambda s: f"T_{s}")


def typedef_chain_st(base_type_st):
    """Generate a typedef chain of length 1-5 ending at a base type.

    Returns (base_type, chain_names, typedefs_dict) where:
    - base_type: the final scalar/struct type name
    - chain_names: list of typedef names [outermost, ..., innermost]
    - typedefs_dict: dict mapping each name to its Type object
    """
    @st.composite
    def _build(draw):
        base = draw(base_type_st)
        chain_len = draw(st.integers(min_value=1, max_value=5))

        # Generate unique names for the chain
        names = []
        for i in range(chain_len):
            name = draw(typedef_name_st.filter(lambda n, ns=names: n not in ns))
            names.append(name)

        # Build typedefs: names[0] -> names[1] -> ... -> names[-1] -> base
        typedefs = {}
        for i in range(chain_len):
            target = base if i == chain_len - 1 else names[i + 1]
            typedefs[names[i]] = _T(base=target)

        return (base, names, typedefs)

    return _build()


# ---------------------------------------------------------------------------
# Property Tests
# ---------------------------------------------------------------------------

class TestTypedefChainResolution:
    """Property 1: Type Resolution Correctness - Typedef chains to scalars.

    **Validates: Requirements 1.1, 1.5**
    """

    @given(data=typedef_chain_st(scalar_type_st))
    @settings(max_examples=100)
    def test_typedef_chain_resolves_to_scalar(self, data):
        """For any typedef chain ending at a scalar, _resolve_full_type
        should return kind='scalar' with the correct base type name."""
        base_type, names, typedefs = data

        ctx = MockSemaCtx(typedefs=typedefs)
        gen = _make_irgen(ctx)

        # Use the outermost typedef name as the declaration type
        decl = _make_decl("x", names[0])
        rt = gen._resolve_full_type(decl)

        assert rt is not None, f"Failed to resolve typedef chain: {names} -> {base_type}"
        assert rt.kind == "scalar", f"Expected scalar, got {rt.kind} for chain {names} -> {base_type}"
        assert rt.name == base_type, f"Expected name '{base_type}', got '{rt.name}'"

        expected_size, expected_float = SCALAR_TYPES[base_type]
        assert rt.size == expected_size, f"Expected size {expected_size}, got {rt.size}"
        assert rt.is_float == expected_float


class TestPointerTypeResolution:
    """Property 1: Type Resolution Correctness - Pointer types.

    **Validates: Requirements 1.3**
    """

    @given(base=scalar_type_st, pointer_level=st.integers(min_value=1, max_value=3))
    @settings(max_examples=100)
    def test_direct_pointer_resolves_correctly(self, base, pointer_level):
        """For any direct pointer declaration, _resolve_full_type should
        return kind='pointer' with size=8."""
        gen = _make_irgen()
        decl = _make_decl("p", base, is_pointer=True, pointer_level=pointer_level)
        rt = gen._resolve_full_type(decl)

        assert rt is not None
        assert rt.kind == "pointer"
        assert rt.size == 8

    @given(data=typedef_chain_st(scalar_type_st))
    @settings(max_examples=100)
    def test_typedef_pointer_resolves_correctly(self, data):
        """For any typedef that resolves to a pointer type, _resolve_full_type
        should return kind='pointer' with size=8."""
        base_type, names, typedefs = data

        # Make the innermost typedef point to a pointer type
        innermost = names[-1]
        typedefs[innermost] = _T(base=base_type, is_pointer=True, pointer_level=1)

        ctx = MockSemaCtx(typedefs=typedefs)
        gen = _make_irgen(ctx)

        decl = _make_decl("p", names[0])
        rt = gen._resolve_full_type(decl)

        assert rt is not None, f"Failed to resolve typedef pointer chain: {names}"
        assert rt.kind == "pointer", f"Expected pointer, got {rt.kind}"
        assert rt.size == 8


class TestArrayTypeResolution:
    """Property 1: Type Resolution Correctness - Array types.

    **Validates: Requirements 1.2**
    """

    @given(
        base=scalar_type_st,
        array_len=st.integers(min_value=1, max_value=100)
    )
    @settings(max_examples=100)
    def test_scalar_array_resolves_correctly(self, base, array_len):
        """For any array of scalars, _resolve_full_type should return
        kind='array' with correct array_length and element_type."""
        gen = _make_irgen()
        decl = _make_decl("arr", base, array_size=array_len)
        rt = gen._resolve_full_type(decl)

        assert rt is not None
        assert rt.kind == "array"
        assert rt.array_length == array_len
        assert rt.element_type is not None
        assert rt.element_type.kind == "scalar"
        assert rt.element_type.name == base

        expected_elem_size = SCALAR_TYPES[base][0]
        assert rt.size == expected_elem_size * array_len

    @given(
        base=scalar_type_st,
        dim1=st.integers(min_value=1, max_value=10),
        dim2=st.integers(min_value=1, max_value=10)
    )
    @settings(max_examples=100)
    def test_multidim_array_resolves_correctly(self, base, dim1, dim2):
        """For any 2D array, _resolve_full_type should return nested array
        types with correct dimensions."""
        gen = _make_irgen()
        decl = _make_decl("matrix", base, array_dims=[dim1, dim2])
        rt = gen._resolve_full_type(decl)

        assert rt is not None
        assert rt.kind == "array"
        assert rt.array_length == dim1

        inner = rt.element_type
        assert inner is not None
        assert inner.kind == "array"
        assert inner.array_length == dim2
        assert inner.element_type.kind == "scalar"
        assert inner.element_type.name == base

        expected_elem_size = SCALAR_TYPES[base][0]
        assert rt.size == dim1 * dim2 * expected_elem_size

    @given(data=typedef_chain_st(scalar_type_st),
           array_len=st.integers(min_value=1, max_value=50))
    @settings(max_examples=100)
    def test_typedef_array_resolves_correctly(self, data, array_len):
        """For any array whose element type is a typedef chain to a scalar,
        _resolve_full_type should resolve the element type correctly."""
        base_type, names, typedefs = data

        ctx = MockSemaCtx(typedefs=typedefs)
        gen = _make_irgen(ctx)

        # Declare array with outermost typedef as element type
        decl = _make_decl("arr", names[0], array_size=array_len)
        rt = gen._resolve_full_type(decl)

        assert rt is not None, f"Failed to resolve typedef array: {names[0]}[{array_len}]"
        assert rt.kind == "array"
        assert rt.array_length == array_len
        assert rt.element_type is not None
        assert rt.element_type.kind == "scalar"
        assert rt.element_type.name == base_type

        expected_elem_size = SCALAR_TYPES[base_type][0]
        assert rt.size == expected_elem_size * array_len


class TestStructUnionTypeResolution:
    """Property 1: Type Resolution Correctness - Struct/union types.

    **Validates: Requirements 1.4**
    """

    @given(
        kind=st.sampled_from(["struct", "union"]),
        num_members=st.integers(min_value=1, max_value=5),
        member_types=st.lists(scalar_type_st, min_size=1, max_size=5)
    )
    @settings(max_examples=100)
    def test_struct_union_resolves_correctly(self, kind, num_members, member_types):
        """For any struct/union with scalar members, _resolve_full_type
        should return the correct kind and populate members."""
        # Ensure we have enough member types
        member_types = member_types[:num_members]
        if len(member_types) < num_members:
            member_types = member_types + [member_types[-1]] * (num_members - len(member_types))

        # Build layout
        member_names = [f"m{i}" for i in range(num_members)]
        offsets = {}
        sizes = {}
        types_map = {}
        offset = 0
        for i, (mname, mtype) in enumerate(zip(member_names, member_types)):
            msize = SCALAR_TYPES[mtype][0]
            offsets[mname] = offset if kind == "struct" else 0
            sizes[mname] = msize
            types_map[mname] = mtype
            if kind == "struct":
                offset += msize

        total_size = offset if kind == "struct" else max(sizes.values())

        type_name = f"{kind} TestType"
        layout = MockStructLayout(
            kind=kind, name="TestType", size=total_size, align=4,
            member_offsets=offsets, member_sizes=sizes, member_types=types_map
        )
        ctx = MockSemaCtx(layouts={type_name: layout})
        gen = _make_irgen(ctx)

        decl = _make_decl("s", type_name)
        rt = gen._resolve_full_type(decl)

        assert rt is not None
        assert rt.kind == kind
        assert rt.name == type_name
        assert rt.size == total_size
        assert rt.members is not None
        assert len(rt.members) == num_members

        # Verify each member has correct type resolution
        for mem_name, mem_offset, mem_size, mem_rtype in rt.members:
            assert mem_name in member_names
            assert mem_rtype is not None
            assert mem_rtype.kind == "scalar"

    @given(data=typedef_chain_st(st.just("struct MockStruct")))
    @settings(max_examples=100)
    def test_typedef_to_struct_resolves_correctly(self, data):
        """For any typedef chain ending at a struct, _resolve_full_type
        should return kind='struct'."""
        base_type, names, typedefs = data

        layout = MockStructLayout(
            kind="struct", name="MockStruct", size=8, align=4,
            member_offsets={"x": 0, "y": 4},
            member_sizes={"x": 4, "y": 4},
            member_types={"x": "int", "y": "int"}
        )
        ctx = MockSemaCtx(typedefs=typedefs, layouts={"struct MockStruct": layout})
        gen = _make_irgen(ctx)

        decl = _make_decl("s", names[0])
        rt = gen._resolve_full_type(decl)

        assert rt is not None, f"Failed to resolve typedef chain to struct: {names}"
        assert rt.kind == "struct"
        assert rt.name == "struct MockStruct"
        assert rt.size == 8
