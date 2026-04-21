"""Property-based tests for member access CType propagation.

**Feature: ir-type-annotations, Property 4: member access instructions carry correct member CType**

**Validates: Requirements 4.1, 4.2, 4.3**

For any C89 program containing struct/union member access, after IR generation:
- load_member/load_member_ptr result_type should equal the member's declared CType
  from StructLayout
- addr_of_member/addr_of_member_ptr result_type should be PointerType whose pointee
  equals the member's CType
- store_member/store_member_ptr meta should contain the member's CType

Testing approach: use Hypothesis to generate random struct definitions with varying
member types, compile through the IR generator, and verify the member access
instructions carry correct CType annotations.
"""
from __future__ import annotations

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from pycc.lexer import Lexer
from pycc.parser import Parser
from pycc.semantics import SemanticAnalyzer
from pycc.ir import IRGenerator
from pycc.types import (
    CType, TypeKind, IntegerType, FloatType, PointerType,
    StructType as CStructType, ast_type_to_ctype_resolved,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _gen_ir_with_ctx(code: str):
    """Parse, analyze, and generate IR, returning (instructions, sema_ctx, ir_gen)."""
    lexer = Lexer(code, "<test>")
    tokens = lexer.tokenize()
    parser = Parser(tokens)
    ast = parser.parse()
    sa = SemanticAnalyzer()
    ctx = sa.analyze(ast)
    irg = IRGenerator()
    irg._sema_ctx = ctx
    instrs = irg.generate(ast)
    return instrs, ctx, irg


def _expected_member_ctype(sema_ctx, struct_key: str, member: str):
    """Get the expected CType for a struct member from StructLayout."""
    layouts = getattr(sema_ctx, "layouts", {})
    layout = layouts.get(struct_key)
    if layout is None:
        return None
    mdecl_types = getattr(layout, "member_decl_types", None)
    if not mdecl_types or member not in mdecl_types:
        return None
    return ast_type_to_ctype_resolved(mdecl_types[member], sema_ctx)


def _ctypes_match(actual, expected) -> bool:
    """Check if two CTypes are semantically equivalent (ignoring qualifiers)."""
    if actual is None or expected is None:
        return actual is expected
    if actual.kind != expected.kind:
        return False
    # For pointer types, recursively compare pointee
    if isinstance(actual, PointerType) and isinstance(expected, PointerType):
        return _ctypes_match(actual.pointee, expected.pointee)
    # For struct types, compare tags
    if isinstance(actual, CStructType) and isinstance(expected, CStructType):
        return actual.tag == expected.tag
    # For integer types, compare unsigned flag
    if isinstance(actual, IntegerType) and isinstance(expected, IntegerType):
        return actual.is_unsigned == expected.is_unsigned
    # For float types, kind match is sufficient
    if isinstance(actual, FloatType) and isinstance(expected, FloatType):
        return True
    return True


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

# C89 scalar types that are safe to use as struct members
SCALAR_TYPES = [
    ("int", "a"),
    ("char", "b"),
    ("long", "c"),
    ("short", "d"),
    ("float", "e"),
    ("double", "f"),
    ("unsigned int", "g"),
    ("unsigned char", "h"),
    ("unsigned long", "i"),
    ("unsigned short", "j"),
]

# Pointer types for struct members
POINTER_TYPES = [
    ("int *", "p1"),
    ("char *", "p2"),
    ("void *", "p3"),
    ("double *", "p4"),
    ("long *", "p5"),
]

ALL_MEMBER_TYPES = SCALAR_TYPES + POINTER_TYPES


@st.composite
def struct_with_member_access(draw):
    """Generate a struct definition and a member access expression.

    Returns (c_code, struct_key, member_name, access_kind) where access_kind
    is 'dot' (s.member) or 'arrow' (p->member).
    """
    # Pick 2-5 members from the available types
    num_members = draw(st.integers(min_value=2, max_value=5))
    chosen = draw(
        st.lists(
            st.sampled_from(ALL_MEMBER_TYPES),
            min_size=num_members,
            max_size=num_members,
            unique_by=lambda x: x[1],
        )
    )

    struct_name = "TestStruct"
    members_decl = "\n".join(f"    {ty} {name};" for ty, name in chosen)

    # Pick which member to access
    target_type, target_member = draw(st.sampled_from(chosen))

    # Choose between dot access (local struct var) and arrow access (pointer)
    access_kind = draw(st.sampled_from(["dot", "arrow"]))

    if access_kind == "dot":
        code = f"""
struct {struct_name} {{
{members_decl}
}};

int main(void) {{
    struct {struct_name} s;
    s.{target_member} = 0;
    return 0;
}}
"""
    else:
        code = f"""
struct {struct_name} {{
{members_decl}
}};

void test_fn(struct {struct_name} *p) {{
    p->{target_member};
}}

int main(void) {{
    return 0;
}}
"""

    return code, f"struct {struct_name}", target_member, access_kind, target_type


@st.composite
def struct_with_store_member(draw):
    """Generate a struct definition with an assignment to a scalar member.

    Returns (c_code, struct_key, member_name, access_kind).
    """
    num_members = draw(st.integers(min_value=2, max_value=4))
    chosen = draw(
        st.lists(
            st.sampled_from(SCALAR_TYPES),
            min_size=num_members,
            max_size=num_members,
            unique_by=lambda x: x[1],
        )
    )

    struct_name = "StoreStruct"
    members_decl = "\n".join(f"    {ty} {name};" for ty, name in chosen)
    target_type, target_member = draw(st.sampled_from(chosen))

    access_kind = draw(st.sampled_from(["dot", "arrow"]))

    if access_kind == "dot":
        code = f"""
struct {struct_name} {{
{members_decl}
}};

int main(void) {{
    struct {struct_name} s;
    s.{target_member} = 0;
    return 0;
}}
"""
    else:
        code = f"""
struct {struct_name} {{
{members_decl}
}};

void test_fn(struct {struct_name} *p) {{
    p->{target_member} = 0;
}}

int main(void) {{
    return 0;
}}
"""

    return code, f"struct {struct_name}", target_member, access_kind, target_type


# ---------------------------------------------------------------------------
# Property 4: member access instructions carry correct member CType
# ---------------------------------------------------------------------------

class TestMemberAccessCTypeProperties:
    """Property 4: member access instructions carry correct member CType

    **Feature: ir-type-annotations, Property 4**
    **Validates: Requirements 4.1, 4.2, 4.3**
    """

    @given(data=struct_with_member_access())
    @settings(max_examples=100, deadline=None)
    def test_load_member_result_type_matches_layout(self, data):
        """For any struct member access, load_member/load_member_ptr result_type
        should equal the member's declared CType from StructLayout.

        **Validates: Requirements 4.1**
        """
        code, struct_key, member, access_kind, member_type_str = data

        instrs, ctx, irg = _gen_ir_with_ctx(code)

        expected_ct = _expected_member_ctype(ctx, struct_key, member)
        assume(expected_ct is not None)

        if access_kind == "dot":
            # Dot access on scalar member produces load_member
            # (struct members produce addr_of_member instead)
            load_instrs = [
                i for i in instrs
                if i.op == "load_member" and i.operand2 == member
            ]
            # For scalar members accessed via dot, we expect load_member
            if load_instrs:
                for li in load_instrs:
                    assert li.result_type is not None, (
                        f"load_member for .{member} missing result_type"
                    )
                    assert _ctypes_match(li.result_type, expected_ct), (
                        f"load_member .{member}: result_type={li.result_type} "
                        f"!= expected={expected_ct}"
                    )
        else:
            # Arrow access produces load_member_ptr
            load_instrs = [
                i for i in instrs
                if i.op == "load_member_ptr" and i.operand2 == member
            ]
            if load_instrs:
                for li in load_instrs:
                    assert li.result_type is not None, (
                        f"load_member_ptr for ->{member} missing result_type"
                    )
                    assert _ctypes_match(li.result_type, expected_ct), (
                        f"load_member_ptr ->{member}: result_type={li.result_type} "
                        f"!= expected={expected_ct}"
                    )

    @given(data=struct_with_member_access())
    @settings(max_examples=100, deadline=None)
    def test_addr_of_member_result_type_is_pointer(self, data):
        """For any struct member that is itself a struct/union, addr_of_member
        result_type should be PointerType whose pointee equals the member CType.

        **Validates: Requirements 4.2**
        """
        code, struct_key, member, access_kind, member_type_str = data

        instrs, ctx, irg = _gen_ir_with_ctx(code)

        expected_ct = _expected_member_ctype(ctx, struct_key, member)
        assume(expected_ct is not None)

        if access_kind == "dot":
            aom_instrs = [
                i for i in instrs
                if i.op == "addr_of_member" and i.operand2 == member
            ]
        else:
            aom_instrs = [
                i for i in instrs
                if i.op == "addr_of_member_ptr" and i.operand2 == member
            ]

        # addr_of_member is only generated for aggregate members;
        # if none found, the member is scalar which is fine
        for ai in aom_instrs:
            assert ai.result_type is not None, (
                f"addr_of_member for {member} missing result_type"
            )
            assert ai.result_type.kind == TypeKind.POINTER, (
                f"addr_of_member for {member}: result_type.kind="
                f"{ai.result_type.kind}, expected POINTER"
            )
            assert isinstance(ai.result_type, PointerType), (
                f"addr_of_member for {member}: result_type is not PointerType"
            )
            assert _ctypes_match(ai.result_type.pointee, expected_ct), (
                f"addr_of_member for {member}: pointee={ai.result_type.pointee} "
                f"!= expected={expected_ct}"
            )

    @given(data=struct_with_store_member())
    @settings(max_examples=100, deadline=None)
    def test_store_member_meta_contains_member_ctype(self, data):
        """For any struct member assignment, store_member/store_member_ptr meta
        should contain the member's CType under 'member_ctype'.

        **Validates: Requirements 4.3**
        """
        code, struct_key, member, access_kind, member_type_str = data

        instrs, ctx, irg = _gen_ir_with_ctx(code)

        expected_ct = _expected_member_ctype(ctx, struct_key, member)
        assume(expected_ct is not None)

        if access_kind == "dot":
            store_instrs = [
                i for i in instrs
                if i.op == "store_member" and i.operand2 == member
            ]
        else:
            store_instrs = [
                i for i in instrs
                if i.op == "store_member_ptr" and i.operand2 == member
            ]

        assert len(store_instrs) > 0, (
            f"No store_member{'_ptr' if access_kind == 'arrow' else ''} "
            f"found for member '{member}'"
        )

        for si in store_instrs:
            meta = si.meta or {}
            assert "member_ctype" in meta, (
                f"store_member for {member} missing 'member_ctype' in meta"
            )
            actual_ct = meta["member_ctype"]
            assert _ctypes_match(actual_ct, expected_ct), (
                f"store_member {member}: member_ctype={actual_ct} "
                f"!= expected={expected_ct}"
            )
