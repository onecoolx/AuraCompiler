"""Unit tests for expression type inference in SemanticAnalyzer._expr_type().

Tests specific examples and edge cases for each expression type:
- MemberAccess (s.member)          — Req 2.1
- PointerMemberAccess (p->member)  — Req 2.2
- FunctionCall (func())            — Req 2.3
- ArrayAccess (arr[i])             — Req 2.4
- UnaryOp * dereference (*ptr)     — Req 2.5
- UnaryOp & address-of (&var)      — Req 2.6
- Cast ((int *)expr)               — Req 2.7
- Pointer vs member access compare — Req 2.8
"""
from __future__ import annotations

import pytest

from pycc.ast_nodes import (
    Type,
    Identifier,
    Cast,
    UnaryOp,
    MemberAccess,
    PointerMemberAccess,
    FunctionCall,
    ArrayAccess,
    LabelAddress,
)
from pycc.semantics import SemanticAnalyzer, StructLayout


# ---------------------------------------------------------------------------
# Helpers (same pattern as property tests)
# ---------------------------------------------------------------------------

def _make_type(base: str, pointer_level: int = 0, **kwargs) -> Type:
    return Type(
        base=base,
        is_pointer=pointer_level > 0,
        pointer_level=pointer_level,
        line=0,
        column=0,
        **kwargs,
    )


def _make_analyzer(**overrides) -> SemanticAnalyzer:
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


def _make_struct_layout(tag, members_spec):
    """Build a StructLayout from a list of (name, Type) pairs."""
    member_offsets = {n: i * 8 for i, (n, _) in enumerate(members_spec)}
    member_sizes = {n: 8 for n, _ in members_spec}
    member_types_str = {n: t.base for n, t in members_spec}
    member_decl_types = {n: t for n, t in members_spec}
    return StructLayout(
        kind="struct", name=tag, size=len(members_spec) * 8, align=8,
        member_offsets=member_offsets, member_sizes=member_sizes,
        member_types=member_types_str, member_decl_types=member_decl_types,
    )


# ---------------------------------------------------------------------------
# Req 2.1: s.member returns member type
# ---------------------------------------------------------------------------

class TestDotMemberAccess:
    """Test _expr_type() on MemberAccess (s.member) expressions."""

    def test_int_member(self):
        """s.x where x is int should return int type."""
        layout = _make_struct_layout("Point", [("x", _make_type("int")), ("y", _make_type("int"))])
        sa = _make_analyzer(
            layouts={"struct Point": layout},
            decl_types={"s": _make_type("struct Point")},
        )
        expr = MemberAccess(
            object=Identifier(name="s", line=1, column=1),
            member="x", line=1, column=1,
        )
        result = sa._expr_type(expr)
        assert result is not None
        assert result.base == "int"
        assert result.pointer_level == 0

    def test_pointer_member(self):
        """s.next where next is struct Node * should return pointer type."""
        layout = _make_struct_layout("Node", [
            ("val", _make_type("int")),
            ("next", _make_type("struct Node", pointer_level=1)),
        ])
        sa = _make_analyzer(
            layouts={"struct Node": layout},
            decl_types={"s": _make_type("struct Node")},
        )
        expr = MemberAccess(
            object=Identifier(name="s", line=1, column=1),
            member="next", line=1, column=1,
        )
        result = sa._expr_type(expr)
        assert result is not None
        assert result.base == "struct Node"
        assert result.pointer_level == 1
        assert result.is_pointer is True

    def test_char_member(self):
        """s.c where c is char should return char type."""
        layout = _make_struct_layout("Data", [("c", _make_type("char")), ("n", _make_type("int"))])
        sa = _make_analyzer(
            layouts={"struct Data": layout},
            decl_types={"d": _make_type("struct Data")},
        )
        expr = MemberAccess(
            object=Identifier(name="d", line=1, column=1),
            member="c", line=1, column=1,
        )
        result = sa._expr_type(expr)
        assert result is not None
        assert result.base == "char"
        assert result.pointer_level == 0


# ---------------------------------------------------------------------------
# Req 2.2: p->member returns member type
# ---------------------------------------------------------------------------

class TestArrowMemberAccess:
    """Test _expr_type() on PointerMemberAccess (p->member) expressions."""

    def test_int_member_via_arrow(self):
        """p->x where x is int should return int type."""
        layout = _make_struct_layout("Point", [("x", _make_type("int")), ("y", _make_type("int"))])
        sa = _make_analyzer(
            layouts={"struct Point": layout},
            decl_types={"p": _make_type("struct Point", pointer_level=1)},
        )
        expr = PointerMemberAccess(
            pointer=Identifier(name="p", line=1, column=1),
            member="x", line=1, column=1,
        )
        result = sa._expr_type(expr)
        assert result is not None
        assert result.base == "int"
        assert result.pointer_level == 0

    def test_double_pointer_member_via_arrow(self):
        """p->buf where buf is char ** should return char ** type."""
        layout = _make_struct_layout("Ctx", [
            ("buf", _make_type("char", pointer_level=2)),
            ("len", _make_type("int")),
        ])
        sa = _make_analyzer(
            layouts={"struct Ctx": layout},
            decl_types={"p": _make_type("struct Ctx", pointer_level=1)},
        )
        expr = PointerMemberAccess(
            pointer=Identifier(name="p", line=1, column=1),
            member="buf", line=1, column=1,
        )
        result = sa._expr_type(expr)
        assert result is not None
        assert result.base == "char"
        assert result.pointer_level == 2


# ---------------------------------------------------------------------------
# Req 2.3: func() returns function return type
# ---------------------------------------------------------------------------

class TestFunctionCallReturnType:
    """Test _expr_type() on FunctionCall expressions."""

    def test_returns_int(self):
        """getval() declared as int getval(void) should return int."""
        ret = _make_type("int")
        sa = _make_analyzer(
            function_full_sig={"getval": ([], ret)},
            function_sigs={"getval": ("int", 0, False)},
        )
        expr = FunctionCall(
            function=Identifier(name="getval", line=1, column=1),
            arguments=[], line=1, column=1,
        )
        result = sa._expr_type(expr)
        assert result is not None
        assert result.base == "int"
        assert result.pointer_level == 0

    def test_returns_pointer(self):
        """malloc-like function returning void * should return void *."""
        ret = _make_type("void", pointer_level=1)
        sa = _make_analyzer(
            function_full_sig={"alloc": ([_make_type("int")], ret)},
            function_sigs={"alloc": ("void", 1, False)},
        )
        expr = FunctionCall(
            function=Identifier(name="alloc", line=1, column=1),
            arguments=[Identifier(name="n", line=1, column=1)],
            line=1, column=1,
        )
        result = sa._expr_type(expr)
        assert result is not None
        assert result.base == "void"
        assert result.pointer_level == 1
        assert result.is_pointer is True

    def test_unknown_function_returns_none(self):
        """Calling an unknown function should return None."""
        sa = _make_analyzer()
        expr = FunctionCall(
            function=Identifier(name="unknown", line=1, column=1),
            arguments=[], line=1, column=1,
        )
        result = sa._expr_type(expr)
        assert result is None


# ---------------------------------------------------------------------------
# Req 2.4: arr[i] returns element type
# ---------------------------------------------------------------------------

class TestArrayAccess:
    """Test _expr_type() on ArrayAccess expressions."""

    def test_int_pointer_subscript(self):
        """arr[i] where arr is int * should return int."""
        sa = _make_analyzer(decl_types={"arr": _make_type("int", pointer_level=1)})
        expr = ArrayAccess(
            array=Identifier(name="arr", line=1, column=1),
            index=Identifier(name="i", line=1, column=1),
            line=1, column=1,
        )
        result = sa._expr_type(expr)
        assert result is not None
        assert result.base == "int"
        assert result.pointer_level == 0
        assert result.is_pointer is False

    def test_double_pointer_subscript(self):
        """pp[0] where pp is char ** should return char *."""
        sa = _make_analyzer(decl_types={"pp": _make_type("char", pointer_level=2)})
        expr = ArrayAccess(
            array=Identifier(name="pp", line=1, column=1),
            index=Identifier(name="i", line=1, column=1),
            line=1, column=1,
        )
        result = sa._expr_type(expr)
        assert result is not None
        assert result.base == "char"
        assert result.pointer_level == 1
        assert result.is_pointer is True

    def test_non_pointer_returns_none(self):
        """arr[i] where arr is plain int should return None."""
        sa = _make_analyzer(decl_types={"x": _make_type("int")})
        expr = ArrayAccess(
            array=Identifier(name="x", line=1, column=1),
            index=Identifier(name="i", line=1, column=1),
            line=1, column=1,
        )
        result = sa._expr_type(expr)
        assert result is None


# ---------------------------------------------------------------------------
# Req 2.5: *ptr returns pointed-to type
# ---------------------------------------------------------------------------

class TestDereference:
    """Test _expr_type() on UnaryOp * (dereference) expressions."""

    def test_deref_int_pointer(self):
        """*p where p is int * should return int."""
        sa = _make_analyzer(decl_types={"p": _make_type("int", pointer_level=1)})
        expr = UnaryOp(
            operator="*",
            operand=Identifier(name="p", line=1, column=1),
            line=1, column=1,
        )
        result = sa._expr_type(expr)
        assert result is not None
        assert result.base == "int"
        assert result.pointer_level == 0
        assert result.is_pointer is False

    def test_deref_double_pointer(self):
        """*pp where pp is int ** should return int *."""
        sa = _make_analyzer(decl_types={"pp": _make_type("int", pointer_level=2)})
        expr = UnaryOp(
            operator="*",
            operand=Identifier(name="pp", line=1, column=1),
            line=1, column=1,
        )
        result = sa._expr_type(expr)
        assert result is not None
        assert result.base == "int"
        assert result.pointer_level == 1
        assert result.is_pointer is True

    def test_deref_non_pointer_returns_none(self):
        """*x where x is plain int should return None."""
        sa = _make_analyzer(decl_types={"x": _make_type("int")})
        expr = UnaryOp(
            operator="*",
            operand=Identifier(name="x", line=1, column=1),
            line=1, column=1,
        )
        result = sa._expr_type(expr)
        assert result is None


# ---------------------------------------------------------------------------
# Req 2.6: &var returns pointer type
# ---------------------------------------------------------------------------

class TestAddressOf:
    """Test _expr_type() on UnaryOp & (address-of) expressions."""

    def test_address_of_int(self):
        """&x where x is int should return int *."""
        sa = _make_analyzer(decl_types={"x": _make_type("int")})
        expr = UnaryOp(
            operator="&",
            operand=Identifier(name="x", line=1, column=1),
            line=1, column=1,
        )
        result = sa._expr_type(expr)
        assert result is not None
        assert result.base == "int"
        assert result.pointer_level == 1
        assert result.is_pointer is True

    def test_address_of_pointer(self):
        """&p where p is char * should return char **."""
        sa = _make_analyzer(decl_types={"p": _make_type("char", pointer_level=1)})
        expr = UnaryOp(
            operator="&",
            operand=Identifier(name="p", line=1, column=1),
            line=1, column=1,
        )
        result = sa._expr_type(expr)
        assert result is not None
        assert result.base == "char"
        assert result.pointer_level == 2
        assert result.is_pointer is True


# ---------------------------------------------------------------------------
# Req 2.7: (int *)expr returns target type
# ---------------------------------------------------------------------------

class TestCast:
    """Test _expr_type() on Cast expressions."""

    def test_cast_to_int_pointer(self):
        """(int *)expr should return int *."""
        sa = _make_analyzer()
        target = _make_type("int", pointer_level=1)
        expr = Cast(
            type=target,
            expression=Identifier(name="x", line=1, column=1),
            line=1, column=1,
        )
        result = sa._expr_type(expr)
        assert result is not None
        assert result.base == "int"
        assert result.pointer_level == 1
        assert result.is_pointer is True

    def test_cast_to_void_pointer(self):
        """(void *)expr should return void *."""
        sa = _make_analyzer()
        target = _make_type("void", pointer_level=1)
        expr = Cast(
            type=target,
            expression=Identifier(name="x", line=1, column=1),
            line=1, column=1,
        )
        result = sa._expr_type(expr)
        assert result is not None
        assert result.base == "void"
        assert result.pointer_level == 1

    def test_cast_to_plain_int(self):
        """(int)expr should return int."""
        sa = _make_analyzer()
        target = _make_type("int")
        expr = Cast(
            type=target,
            expression=Identifier(name="x", line=1, column=1),
            line=1, column=1,
        )
        result = sa._expr_type(expr)
        assert result is not None
        assert result.base == "int"
        assert result.pointer_level == 0
        assert result.is_pointer is False


# ---------------------------------------------------------------------------
# Req 2.8: pointer vs member access comparison should not error
# ---------------------------------------------------------------------------

class TestPointerMemberAccessComparison:
    """Test that comparing a pointer with a member access result does not
    produce a semantic error (end-to-end via Compiler)."""

    def test_pointer_vs_member_access_no_error(self, tmp_path):
        """A C program comparing a pointer with a struct member pointer
        should compile without semantic errors."""
        from pycc.compiler import Compiler

        src = tmp_path / "test.c"
        src.write_text(
            "struct Node { struct Node *next; };\n"
            "int main(void) {\n"
            "    struct Node n;\n"
            "    struct Node *p;\n"
            "    p = (struct Node *)0;\n"
            "    n.next = p;\n"
            "    if (p == n.next) { return 0; }\n"
            "    return 1;\n"
            "}\n"
        )
        compiler = Compiler()
        # compile_code reads from file path
        asm = compiler.compile_code(src.read_text())
        # If we got here without exception, the comparison was accepted.
        assert asm is not None


# ---------------------------------------------------------------------------
# LabelAddress: &&label returns void *
# ---------------------------------------------------------------------------

class TestLabelAddress:
    """Test _expr_type() on LabelAddress (&&label) expressions."""

    def test_label_address_returns_void_pointer(self):
        """&&label should return void * type."""
        sa = _make_analyzer()
        expr = LabelAddress(label_name="target", line=1, column=1)
        result = sa._expr_type(expr)
        assert result is not None
        assert result.base == "void"
        assert result.pointer_level == 1
        assert result.is_pointer is True

    def test_label_address_different_labels_same_type(self):
        """&&foo and &&bar should both return void * type."""
        sa = _make_analyzer()
        expr1 = LabelAddress(label_name="foo", line=1, column=1)
        expr2 = LabelAddress(label_name="bar", line=2, column=1)
        r1 = sa._expr_type(expr1)
        r2 = sa._expr_type(expr2)
        assert r1 is not None and r2 is not None
        assert r1.base == r2.base == "void"
        assert r1.pointer_level == r2.pointer_level == 1
        assert r1.is_pointer is True and r2.is_pointer is True
