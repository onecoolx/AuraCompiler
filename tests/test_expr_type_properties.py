"""Property-based tests for expression type inference in SemanticAnalyzer._expr_type().

**Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7**

Uses Hypothesis to verify that _expr_type() correctly infers types for
member access, function calls, dereference/address-of, array access, and casts.
"""
from __future__ import annotations

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from pycc.ast_nodes import (
    Type,
    Identifier,
    Cast,
    UnaryOp,
    MemberAccess,
    PointerMemberAccess,
    FunctionCall,
    ArrayAccess,
    Declaration,
    Expression,
)
from pycc.semantics import SemanticAnalyzer, StructLayout


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_analyzer(**overrides) -> SemanticAnalyzer:
    """Create a SemanticAnalyzer with minimal internal state for _expr_type() testing."""
    sa = SemanticAnalyzer()
    sa._scopes = [{}]
    sa._typedefs = [{}]
    sa._layouts = overrides.get("layouts", {})
    sa._function_sigs = overrides.get("function_sigs", {})
    sa._function_full_sig = overrides.get("function_full_sig", {})
    sa._function_param_types = {}
    sa._global_types = {}
    sa._global_decl_types = overrides.get("global_decl_types", {})
    sa._decl_types = overrides.get("decl_types", {})
    sa._enum_constants = {}
    sa.errors = []
    sa.warnings = []
    return sa


def _make_type(base: str, pointer_level: int = 0, **kwargs) -> Type:
    """Create a Type node with consistent is_pointer / pointer_level."""
    ty = Type(
        base=base,
        is_pointer=pointer_level > 0,
        pointer_level=pointer_level,
        line=0,
        column=0,
        **kwargs,
    )
    return ty


# ---------------------------------------------------------------------------
# Strategies (smart generators)
# ---------------------------------------------------------------------------

_C89_BASE_TYPES = ["int", "char", "short", "long", "float", "double", "unsigned int",
                   "unsigned char", "unsigned short", "unsigned long"]

_base_type_st = st.sampled_from(_C89_BASE_TYPES)

_pointer_level_st = st.integers(min_value=0, max_value=4)

_struct_tag_st = st.sampled_from(["S", "T", "Node", "Point", "Data", "Buf", "Ctx"])

_member_name_st = st.sampled_from(["x", "y", "val", "data", "next", "ptr", "len", "buf", "id", "flag"])

_var_name_st = st.sampled_from(["a", "b", "c", "s", "p", "q", "v", "w", "obj", "tmp"])

_func_name_st = st.sampled_from(["foo", "bar", "baz", "get", "set", "init", "calc", "run"])


@st.composite
def _random_type(draw) -> Type:
    """Generate a random Type with base type and pointer level."""
    base = draw(_base_type_st)
    plevel = draw(_pointer_level_st)
    return _make_type(base, plevel)


@st.composite
def _struct_member_spec(draw):
    """Generate a struct member: (member_name, member_type)."""
    name = draw(_member_name_st)
    ty = draw(_random_type())
    return name, ty


@st.composite
def _struct_with_members(draw):
    """Generate a struct tag and 1-5 members with unique names."""
    tag = draw(_struct_tag_st)
    count = draw(st.integers(min_value=1, max_value=5))
    all_names = ["x", "y", "val", "data", "next", "ptr", "len", "buf", "id", "flag"]
    names = draw(st.permutations(all_names).map(lambda ns: ns[:count]))
    members = []
    for n in names:
        ty = draw(_random_type())
        members.append((n, ty))
    return tag, members


# ---------------------------------------------------------------------------
# Property 4: 成员访问类型推断
# Feature: parser-semantics-hardening, Property 4: member access type inference
# ---------------------------------------------------------------------------

class TestMemberAccessTypeInference:
    """Property 4: 成员访问类型推断

    For any declared struct and its members, calling _expr_type() on a
    MemberAccess (.) or PointerMemberAccess (->) expression should return
    the member's declared type.

    **Validates: Requirements 2.1, 2.2**
    """

    @given(data=st.data(), struct_info=_struct_with_members())
    @settings(max_examples=200, deadline=None)
    def test_dot_member_access_returns_member_type(self, data, struct_info):
        """s.member returns the member's declared type.

        **Validates: Requirements 2.1**
        """
        tag, members = struct_info
        # Pick a random member to access
        idx = data.draw(st.integers(min_value=0, max_value=len(members) - 1))
        member_name, member_type = members[idx]

        # Build struct layout
        key = f"struct {tag}"
        member_offsets = {n: i * 8 for i, (n, _) in enumerate(members)}
        member_sizes = {n: 8 for n, _ in members}
        member_types_str = {n: t.base for n, t in members}
        member_decl_types = {n: t for n, t in members}
        layout = StructLayout(
            kind="struct", name=tag, size=len(members) * 8, align=8,
            member_offsets=member_offsets, member_sizes=member_sizes,
            member_types=member_types_str, member_decl_types=member_decl_types,
        )

        # Set up analyzer: variable 's' has type 'struct Tag'
        var_name = "s"
        var_type = _make_type(f"struct {tag}", pointer_level=0)
        sa = _make_analyzer(
            layouts={key: layout},
            decl_types={var_name: var_type},
        )

        # Build MemberAccess: s.member
        expr = MemberAccess(
            object=Identifier(name=var_name, line=1, column=1),
            member=member_name,
            line=1, column=1,
        )
        result = sa._expr_type(expr)

        assert result is not None, (
            f"_expr_type returned None for {var_name}.{member_name}\n"
            f"Struct: {key}, members: {[n for n, _ in members]}"
        )
        assert result.base == member_type.base, (
            f"Expected base={member_type.base!r}, got {result.base!r}\n"
            f"Expression: {var_name}.{member_name}"
        )
        assert result.pointer_level == member_type.pointer_level, (
            f"Expected pointer_level={member_type.pointer_level}, got {result.pointer_level}\n"
            f"Expression: {var_name}.{member_name}"
        )

    @given(data=st.data(), struct_info=_struct_with_members())
    @settings(max_examples=200, deadline=None)
    def test_arrow_member_access_returns_member_type(self, data, struct_info):
        """p->member returns the member's declared type.

        **Validates: Requirements 2.2**
        """
        tag, members = struct_info
        idx = data.draw(st.integers(min_value=0, max_value=len(members) - 1))
        member_name, member_type = members[idx]

        key = f"struct {tag}"
        member_offsets = {n: i * 8 for i, (n, _) in enumerate(members)}
        member_sizes = {n: 8 for n, _ in members}
        member_types_str = {n: t.base for n, t in members}
        member_decl_types = {n: t for n, t in members}
        layout = StructLayout(
            kind="struct", name=tag, size=len(members) * 8, align=8,
            member_offsets=member_offsets, member_sizes=member_sizes,
            member_types=member_types_str, member_decl_types=member_decl_types,
        )

        # Variable 'p' is a pointer to struct Tag
        var_name = "p"
        var_type = _make_type(f"struct {tag}", pointer_level=1)
        sa = _make_analyzer(
            layouts={key: layout},
            decl_types={var_name: var_type},
        )

        # Build PointerMemberAccess: p->member
        expr = PointerMemberAccess(
            pointer=Identifier(name=var_name, line=1, column=1),
            member=member_name,
            line=1, column=1,
        )
        result = sa._expr_type(expr)

        assert result is not None, (
            f"_expr_type returned None for {var_name}->{member_name}\n"
            f"Struct: {key}, members: {[n for n, _ in members]}"
        )
        assert result.base == member_type.base, (
            f"Expected base={member_type.base!r}, got {result.base!r}\n"
            f"Expression: {var_name}->{member_name}"
        )
        assert result.pointer_level == member_type.pointer_level, (
            f"Expected pointer_level={member_type.pointer_level}, got {result.pointer_level}\n"
            f"Expression: {var_name}->{member_name}"
        )


# ---------------------------------------------------------------------------
# Property 5: 函数调用返回类型推断
# Feature: parser-semantics-hardening, Property 5: function call return type inference
# ---------------------------------------------------------------------------

class TestFunctionCallReturnTypeInference:
    """Property 5: 函数调用返回类型推断

    For any declared function, calling _expr_type() on a FunctionCall
    expression targeting that function should return the function's declared
    return type.

    **Validates: Requirements 2.3**
    """

    @given(
        func_name=_func_name_st,
        ret_type=_random_type(),
        param_count=st.integers(min_value=0, max_value=4),
    )
    @settings(max_examples=200, deadline=None)
    def test_function_call_returns_declared_return_type(
        self, func_name: str, ret_type: Type, param_count: int,
    ):
        """FunctionCall returns the function's declared return type.

        **Validates: Requirements 2.3**
        """
        # Build param types list
        param_types = [_make_type("int") for _ in range(param_count)]

        sa = _make_analyzer(
            function_full_sig={func_name: (param_types, ret_type)},
            function_sigs={func_name: (ret_type.base, param_count, False)},
        )

        # Build FunctionCall: func_name(arg1, arg2, ...)
        args = [Identifier(name=f"a{i}", line=1, column=1) for i in range(param_count)]
        expr = FunctionCall(
            function=Identifier(name=func_name, line=1, column=1),
            arguments=args,
            line=1, column=1,
        )
        result = sa._expr_type(expr)

        assert result is not None, (
            f"_expr_type returned None for call to {func_name}()\n"
            f"Expected return type: {ret_type.base} {'*' * ret_type.pointer_level}"
        )
        assert result.base == ret_type.base, (
            f"Expected return base={ret_type.base!r}, got {result.base!r}\n"
            f"Function: {func_name}"
        )
        assert result.pointer_level == ret_type.pointer_level, (
            f"Expected return pointer_level={ret_type.pointer_level}, got {result.pointer_level}\n"
            f"Function: {func_name}"
        )


# ---------------------------------------------------------------------------
# Property 6: 间接层级移除
# Feature: parser-semantics-hardening, Property 6: indirection level removal
# ---------------------------------------------------------------------------

class TestIndirectionLevelRemoval:
    """Property 6: 间接层级移除

    For any pointer type expression (pointer_level >= 1), applying ArrayAccess
    or UnaryOp * dereference should result in _expr_type() returning a type
    with pointer_level = original - 1.

    **Validates: Requirements 2.4, 2.5**
    """

    @given(
        var_name=_var_name_st,
        base=_base_type_st,
        plevel=st.integers(min_value=1, max_value=4),
    )
    @settings(max_examples=200, deadline=None)
    def test_array_access_decrements_pointer_level(
        self, var_name: str, base: str, plevel: int,
    ):
        """arr[i] on a pointer type returns pointer_level - 1.

        **Validates: Requirements 2.4**
        """
        var_type = _make_type(base, pointer_level=plevel)
        sa = _make_analyzer(decl_types={var_name: var_type})

        expr = ArrayAccess(
            array=Identifier(name=var_name, line=1, column=1),
            index=Identifier(name="i", line=1, column=1),
            line=1, column=1,
        )
        result = sa._expr_type(expr)

        assert result is not None, (
            f"_expr_type returned None for {var_name}[i]\n"
            f"Variable type: {base} {'*' * plevel}"
        )
        assert result.base == base, (
            f"Expected base={base!r}, got {result.base!r}"
        )
        expected_level = plevel - 1
        assert result.pointer_level == expected_level, (
            f"Expected pointer_level={expected_level}, got {result.pointer_level}\n"
            f"Original pointer_level={plevel}"
        )
        assert result.is_pointer == (expected_level > 0), (
            f"Expected is_pointer={expected_level > 0}, got {result.is_pointer}"
        )

    @given(
        var_name=_var_name_st,
        base=_base_type_st,
        plevel=st.integers(min_value=1, max_value=4),
    )
    @settings(max_examples=200, deadline=None)
    def test_deref_decrements_pointer_level(
        self, var_name: str, base: str, plevel: int,
    ):
        """*ptr on a pointer type returns pointer_level - 1.

        **Validates: Requirements 2.5**
        """
        var_type = _make_type(base, pointer_level=plevel)
        sa = _make_analyzer(decl_types={var_name: var_type})

        expr = UnaryOp(
            operator="*",
            operand=Identifier(name=var_name, line=1, column=1),
            line=1, column=1,
        )
        result = sa._expr_type(expr)

        assert result is not None, (
            f"_expr_type returned None for *{var_name}\n"
            f"Variable type: {base} {'*' * plevel}"
        )
        assert result.base == base, (
            f"Expected base={base!r}, got {result.base!r}"
        )
        expected_level = plevel - 1
        assert result.pointer_level == expected_level, (
            f"Expected pointer_level={expected_level}, got {result.pointer_level}\n"
            f"Original pointer_level={plevel}"
        )
        assert result.is_pointer == (expected_level > 0), (
            f"Expected is_pointer={expected_level > 0}, got {result.is_pointer}"
        )


# ---------------------------------------------------------------------------
# Property 7: 取地址增加指针层级
# Feature: parser-semantics-hardening, Property 7: address-of increases pointer level
# ---------------------------------------------------------------------------

class TestAddressOfIncreasesPointerLevel:
    """Property 7: 取地址增加指针层级

    For any expression with a known type, applying UnaryOp & should result
    in _expr_type() returning a type with pointer_level = original + 1.

    **Validates: Requirements 2.6**
    """

    @given(
        var_name=_var_name_st,
        base=_base_type_st,
        plevel=st.integers(min_value=0, max_value=3),
    )
    @settings(max_examples=200, deadline=None)
    def test_address_of_increments_pointer_level(
        self, var_name: str, base: str, plevel: int,
    ):
        """&expr returns pointer_level + 1.

        **Validates: Requirements 2.6**
        """
        var_type = _make_type(base, pointer_level=plevel)
        sa = _make_analyzer(decl_types={var_name: var_type})

        expr = UnaryOp(
            operator="&",
            operand=Identifier(name=var_name, line=1, column=1),
            line=1, column=1,
        )
        result = sa._expr_type(expr)

        assert result is not None, (
            f"_expr_type returned None for &{var_name}\n"
            f"Variable type: {base} {'*' * plevel}"
        )
        assert result.base == base, (
            f"Expected base={base!r}, got {result.base!r}"
        )
        expected_level = plevel + 1
        assert result.pointer_level == expected_level, (
            f"Expected pointer_level={expected_level}, got {result.pointer_level}\n"
            f"Original pointer_level={plevel}"
        )
        assert result.is_pointer is True, (
            f"Expected is_pointer=True after address-of, got {result.is_pointer}"
        )


# ---------------------------------------------------------------------------
# Property 8: Cast 返回目标类型
# Feature: parser-semantics-hardening, Property 8: cast returns target type
# ---------------------------------------------------------------------------

class TestCastReturnsTargetType:
    """Property 8: Cast 返回目标类型

    For any Cast expression, _expr_type() should return the same type as
    the Cast's to_type field (which is stored as expr.type on Cast nodes).

    **Validates: Requirements 2.7**
    """

    @given(
        target_type=_random_type(),
        src_base=_base_type_st,
        src_plevel=_pointer_level_st,
    )
    @settings(max_examples=200, deadline=None)
    def test_cast_returns_target_type(
        self, target_type: Type, src_base: str, src_plevel: int,
    ):
        """(target_type)expr returns target_type.

        **Validates: Requirements 2.7**
        """
        sa = _make_analyzer()

        # Build Cast expression: (target_type)some_expr
        inner_expr = Identifier(name="x", line=1, column=1)
        # Cast node stores the target type in its 'type' field
        expr = Cast(
            type=target_type,
            expression=inner_expr,
            line=1, column=1,
        )
        result = sa._expr_type(expr)

        assert result is not None, (
            f"_expr_type returned None for cast to {target_type.base} {'*' * target_type.pointer_level}"
        )
        assert result.base == target_type.base, (
            f"Expected base={target_type.base!r}, got {result.base!r}"
        )
        assert result.pointer_level == target_type.pointer_level, (
            f"Expected pointer_level={target_type.pointer_level}, got {result.pointer_level}"
        )
        assert result.is_pointer == target_type.is_pointer, (
            f"Expected is_pointer={target_type.is_pointer}, got {result.is_pointer}"
        )
