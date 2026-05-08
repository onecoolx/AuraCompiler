"""Property-based tests for IR generator array type handling.

**Validates: Requirements 4.1, 4.2, 4.3, 5.4**

Property 7: For any Identifier reference whose declared type has is_array=True,
the IR generator SHALL emit a mov_addr instruction (address decay), not a load.

Property 8: For any array type, sizeof SHALL equal
product(array_dimensions) * sizeof(element_type).

Property 9: For any struct member declared as an array,
layout.member_decl_types[member_name] SHALL have is_array=True and
array_element_type correctly reflecting the element type.
"""
from __future__ import annotations

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from pycc.ast_nodes import Type
from pycc.lexer import Lexer
from pycc.parser import Parser
from pycc.semantics import SemanticAnalyzer
from pycc.ir import IRGenerator


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Base types that the compiler handles correctly for arrays
BASE_TYPE_MAP = {
    "int": "int",
    "char": "char",
    "long": "long int",
    "short": "short int",
}

_base_type_keys = st.sampled_from(list(BASE_TYPE_MAP.keys()))

# Element sizes for computing expected sizeof
ELEM_SIZES = {
    "int": 4,
    "char": 1,
    "long": 8,
    "short": 2,
}

# Dimension sizes: 1-20
_dim_size = st.integers(min_value=1, max_value=20)

# 1 to 2 dimensions
_array_dims_1d = st.lists(_dim_size, min_size=1, max_size=1)
_array_dims_1_2d = st.lists(_dim_size, min_size=1, max_size=2)

# Variable names
_var_names = st.sampled_from(["arr", "buf", "data", "vals"])

# Struct member names
_member_names = st.sampled_from(["data", "buf", "items", "vals"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _compile_to_ir(code: str):
    """Compile C code through the full pipeline and return IR instructions + generator."""
    lexer = Lexer(code)
    tokens = lexer.tokenize()
    parser = Parser(tokens)
    ast = parser.parse()
    analyzer = SemanticAnalyzer()
    sema_ctx = analyzer.analyze(ast)
    gen = IRGenerator()
    gen._sema_ctx = sema_ctx
    ir = gen.generate(ast)
    return ir, gen, sema_ctx


# ---------------------------------------------------------------------------
# Composite strategies
# ---------------------------------------------------------------------------

@st.composite
def local_array_code(draw):
    """Generate C code with a local array declaration and a reference to it.

    Returns (code, var_name, base_type_key) where:
    - code is valid C with a function containing a local array and a pointer assignment
    - var_name is the array variable name
    - base_type_key is the source type key (e.g. "int")
    """
    base = draw(_base_type_keys)
    name = draw(_var_names)
    dims = draw(_array_dims_1d)
    dims_str = "".join(f"[{d}]" for d in dims)
    # Create a function that declares the array and assigns it to a pointer
    # This forces the Identifier reference to the array (triggering decay)
    code = f"void test_fn(void) {{ {base} {name}{dims_str}; {base} *p = {name}; }}\n"
    return code, name, base


@st.composite
def sizeof_array_code(draw):
    """Generate C code with sizeof(array_variable).

    Returns (code, var_name, base_type_key, dims) where:
    - code is valid C with a function that uses sizeof on a local array
    - dims is the list of dimension sizes
    """
    base = draw(_base_type_keys)
    name = draw(_var_names)
    dims = draw(_array_dims_1_2d)
    dims_str = "".join(f"[{d}]" for d in dims)
    # sizeof(name) should return total array size
    code = f"void test_fn(void) {{ {base} {name}{dims_str}; int sz = sizeof({name}); }}\n"
    return code, name, base, dims


@st.composite
def struct_with_array_member(draw):
    """Generate C code with a struct containing an array member.

    Returns (code, struct_tag, member_name, base_type_key, dims)
    """
    base = draw(_base_type_keys)
    member = draw(_member_names)
    dims = draw(_array_dims_1_2d)
    dims_str = "".join(f"[{d}]" for d in dims)
    code = f"struct TestS {{ {base} {member}{dims_str}; }};\n"
    return code, "struct TestS", member, base, dims


# ---------------------------------------------------------------------------
# Property Tests
# ---------------------------------------------------------------------------

class TestProperty7IRGenArrayMovAddr:
    """Feature: array-pointer-distinction, Property 7: IR gen emits mov_addr for arrays

    For any Identifier reference whose declared type has is_array=True,
    the IR generator SHALL emit a mov_addr instruction (address decay),
    rather than a load instruction.

    **Validates: Requirements 4.1**
    """

    @settings(max_examples=100)
    @given(data=local_array_code())
    def test_local_array_reference_emits_mov_addr(self, data):
        """Feature: array-pointer-distinction, Property 7: IR gen emits mov_addr for arrays"""
        code, var_name, base_type = data

        ir, gen, sema_ctx = _compile_to_ir(code)

        # Verify that the array variable's Type has is_array=True
        ast_ty = gen._local_ast_types.get(var_name)
        assert ast_ty is not None, (
            f"Expected '{var_name}' in _local_ast_types after IR generation"
        )
        assert getattr(ast_ty, "is_array", False), (
            f"Expected is_array=True for '{var_name}', got {ast_ty}"
        )

        # Find mov_addr instruction for this variable within test_fn
        in_fn = False
        found_mov_addr = False
        for inst in ir:
            if inst.op == "func_begin" and inst.label == "test_fn":
                in_fn = True
            elif inst.op == "func_end":
                in_fn = False
            if in_fn and inst.op == "mov_addr":
                if inst.operand1 and var_name in inst.operand1:
                    found_mov_addr = True
                    break

        assert found_mov_addr, (
            f"Expected mov_addr for local array '{var_name}' "
            f"(type: {base_type}{{}}) but none found in IR"
        )

        # Verify NO load instruction was emitted for this array variable
        # (load would mean treating it as a scalar/pointer, not an array)
        in_fn = False
        for inst in ir:
            if inst.op == "func_begin" and inst.label == "test_fn":
                in_fn = True
            elif inst.op == "func_end":
                in_fn = False
            if in_fn and inst.op == "load":
                if inst.operand1 and var_name in inst.operand1:
                    # A load of the array variable itself is wrong
                    assert False, (
                        f"Found 'load' for array variable '{var_name}' — "
                        f"should be mov_addr instead"
                    )


class TestProperty8SizeofArrayType:
    """Feature: array-pointer-distinction, Property 8: sizeof computes array total size

    For any array type, sizeof SHALL equal
    product(array_dimensions) * sizeof(element_type).

    **Validates: Requirements 4.2**
    """

    @settings(max_examples=100)
    @given(data=sizeof_array_code())
    def test_sizeof_array_equals_product_dims_times_elem_size(self, data):
        """Feature: array-pointer-distinction, Property 8: sizeof computes array total size"""
        code, var_name, base_type, dims = data

        ir, gen, sema_ctx = _compile_to_ir(code)

        # Compute expected size: product(dims) * element_size
        total_elems = 1
        for d in dims:
            total_elems *= d
        elem_size = ELEM_SIZES[base_type]
        expected_size = total_elems * elem_size

        # Find the mov instruction that stores sizeof result into @sz
        # The IR should contain: mov @sz, $<expected_size>
        # or an equivalent assignment of the sizeof value.
        in_fn = False
        sizeof_value = None
        for inst in ir:
            if inst.op == "func_begin" and inst.label == "test_fn":
                in_fn = True
            elif inst.op == "func_end":
                in_fn = False
            if in_fn and inst.op == "mov":
                # Look for mov @sz, $N or mov to a temp that feeds @sz
                if inst.result and "sz" in inst.result:
                    if inst.operand1 and inst.operand1.startswith("$"):
                        sizeof_value = int(inst.operand1[1:])
                        break
                # Also check if operand1 is the sizeof immediate
                if inst.operand1 and inst.operand1.startswith("$"):
                    val = int(inst.operand1[1:])
                    if val == expected_size:
                        # Could be the sizeof result being moved
                        sizeof_value = val

        # If we didn't find it via mov to @sz, search for the immediate value
        # in any instruction that feeds into the sz variable
        if sizeof_value is None:
            in_fn = False
            for inst in ir:
                if inst.op == "func_begin" and inst.label == "test_fn":
                    in_fn = True
                elif inst.op == "func_end":
                    in_fn = False
                if in_fn and inst.op == "mov" and inst.operand1:
                    if inst.operand1 == f"${expected_size}":
                        sizeof_value = expected_size
                        break

        assert sizeof_value is not None, (
            f"Could not find sizeof result in IR for '{base_type} {var_name}"
            f"{''.join(f'[{d}]' for d in dims)}'. "
            f"Expected ${expected_size}"
        )
        assert sizeof_value == expected_size, (
            f"sizeof({var_name}) = {sizeof_value}, "
            f"expected {expected_size} "
            f"(product({dims}) * {elem_size})"
        )


class TestProperty9StructMemberArrayType:
    """Feature: array-pointer-distinction, Property 9: Struct member array info in Type

    For any struct member declared as an array,
    layout.member_decl_types[member_name] SHALL have is_array=True
    and array_element_type correctly reflecting the element type.

    **Validates: Requirements 4.3, 5.4**
    """

    @settings(max_examples=100)
    @given(data=struct_with_array_member())
    def test_struct_member_array_has_is_array_true(self, data):
        """Feature: array-pointer-distinction, Property 9: Struct member array info in Type"""
        code, struct_tag, member_name, base_type, dims = data

        # Parse and analyze to get the layout
        lexer = Lexer(code)
        tokens = lexer.tokenize()
        parser = Parser(tokens)
        ast = parser.parse()
        analyzer = SemanticAnalyzer()
        sema_ctx = analyzer.analyze(ast)

        # Get the struct layout
        layout = sema_ctx.layouts.get(struct_tag)
        assert layout is not None, (
            f"Expected layout for '{struct_tag}' in sema_ctx.layouts"
        )

        # Check member_decl_types
        mdecl_types = getattr(layout, "member_decl_types", None)
        assert mdecl_types is not None, (
            f"Expected member_decl_types in layout for '{struct_tag}'"
        )
        assert member_name in mdecl_types, (
            f"Expected '{member_name}' in member_decl_types"
        )

        member_type = mdecl_types[member_name]

        # Property: is_array must be True
        assert getattr(member_type, "is_array", False) is True, (
            f"Expected is_array=True for struct member '{member_name}', "
            f"got Type: {member_type}"
        )

        # Property: array_element_type must be non-None
        elem_type = getattr(member_type, "array_element_type", None)
        assert elem_type is not None, (
            f"Expected non-None array_element_type for array member '{member_name}'"
        )

        # Property: leaf element type base matches declared base type
        leaf = elem_type
        while getattr(leaf, "is_array", False) and getattr(leaf, "array_element_type", None):
            leaf = leaf.array_element_type

        expected_base = BASE_TYPE_MAP[base_type]
        assert leaf.base == expected_base, (
            f"Expected leaf element base='{expected_base}', "
            f"got '{leaf.base}' for member '{member_name}'"
        )

    @settings(max_examples=100)
    @given(data=struct_with_array_member())
    def test_struct_member_array_dimensions_correct(self, data):
        """Feature: array-pointer-distinction, Property 9: Struct member array dimensions"""
        code, struct_tag, member_name, base_type, dims = data

        lexer = Lexer(code)
        tokens = lexer.tokenize()
        parser = Parser(tokens)
        ast = parser.parse()
        analyzer = SemanticAnalyzer()
        sema_ctx = analyzer.analyze(ast)

        layout = sema_ctx.layouts.get(struct_tag)
        assert layout is not None
        mdecl_types = getattr(layout, "member_decl_types", None)
        assert mdecl_types is not None
        member_type = mdecl_types[member_name]

        # array_dimensions should match the declared dimensions
        actual_dims = getattr(member_type, "array_dimensions", None)
        assert actual_dims is not None, (
            f"Expected non-None array_dimensions for array member '{member_name}'"
        )
        assert actual_dims == dims, (
            f"Expected array_dimensions={dims}, got {actual_dims} "
            f"for member '{member_name}'"
        )
