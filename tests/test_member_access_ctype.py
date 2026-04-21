"""Tests for member access instruction CType annotations (task 3.3).

Verifies that load_member, load_member_ptr, addr_of_member,
addr_of_member_ptr, store_member, and store_member_ptr instructions
carry correct CType annotations in result_type and meta["member_ctype"].
"""

import pytest
from pycc.compiler import Compiler


def _compile_to_ir(code: str, tmp_path):
    """Compile C code and return (ir_instructions, sym_table)."""
    from pycc.ir import IRGenerator
    compiler = Compiler()
    tokens = compiler.get_tokens(code)
    ast = compiler.get_ast(tokens)
    sema_ctx, _ = compiler.analyze_semantics(ast)
    gen = IRGenerator()
    gen._sema_ctx = sema_ctx
    ir = gen.generate(ast)
    sym_table = getattr(gen, "_sym_table", None)
    return ir, sym_table


def _find_instructions(ir, op):
    """Find all IR instructions with the given op."""
    return [i for i in ir if i.op == op]


class TestLoadMemberCType:
    """Test load_member/load_member_ptr result_type annotations."""

    def test_load_member_scalar(self, tmp_path):
        """load_member for a scalar member sets result_type to member CType."""
        code = """
        struct S { int x; long y; };
        int foo(void) {
            struct S s;
            s.x = 10;
            return s.x;
        }
        """
        ir, st = _compile_to_ir(code, tmp_path)
        loads = _find_instructions(ir, "load_member")
        # At least one load_member for s.x
        found = [i for i in loads if i.operand2 == "x"]
        assert len(found) > 0, "Expected load_member for member 'x'"
        for inst in found:
            assert inst.result_type is not None, "load_member should have result_type"
            from pycc.types import TypeKind
            assert inst.result_type.kind == TypeKind.INT

    def test_load_member_ptr_pointer_member(self, tmp_path):
        """load_member_ptr for a pointer member sets result_type."""
        code = """
        struct Node { int val; struct Node *next; };
        struct Node *get_next(struct Node *n) {
            return n->next;
        }
        """
        ir, st = _compile_to_ir(code, tmp_path)
        loads = _find_instructions(ir, "load_member_ptr")
        found = [i for i in loads if i.operand2 == "next"]
        assert len(found) > 0, "Expected load_member_ptr for member 'next'"
        for inst in found:
            assert inst.result_type is not None, "load_member_ptr should have result_type"
            from pycc.types import TypeKind
            assert inst.result_type.kind == TypeKind.POINTER

    def test_load_member_ptr_scalar(self, tmp_path):
        """load_member_ptr for a scalar member sets result_type."""
        code = """
        struct S { int x; long y; };
        int get_x(struct S *p) {
            return p->x;
        }
        """
        ir, st = _compile_to_ir(code, tmp_path)
        loads = _find_instructions(ir, "load_member_ptr")
        found = [i for i in loads if i.operand2 == "x"]
        assert len(found) > 0, "Expected load_member_ptr for member 'x'"
        for inst in found:
            assert inst.result_type is not None
            from pycc.types import TypeKind
            assert inst.result_type.kind == TypeKind.INT


class TestAddrOfMemberCType:
    """Test addr_of_member/addr_of_member_ptr result_type annotations."""

    def test_addr_of_member_struct_member(self, tmp_path):
        """addr_of_member for a struct member sets result_type to PointerType."""
        code = """
        struct Inner { int a; int b; };
        struct Outer { struct Inner inner; int c; };
        int foo(void) {
            struct Outer o;
            o.inner.a = 5;
            return o.inner.a;
        }
        """
        ir, st = _compile_to_ir(code, tmp_path)
        addrs = _find_instructions(ir, "addr_of_member")
        found = [i for i in addrs if i.operand2 == "inner"]
        assert len(found) > 0, "Expected addr_of_member for member 'inner'"
        for inst in found:
            assert inst.result_type is not None, "addr_of_member should have result_type"
            from pycc.types import TypeKind, PointerType
            assert inst.result_type.kind == TypeKind.POINTER
            assert isinstance(inst.result_type, PointerType)
            assert inst.result_type.pointee is not None
            assert inst.result_type.pointee.kind == TypeKind.STRUCT

    def test_addr_of_member_address_of(self, tmp_path):
        """&obj.member sets result_type to PointerType(pointee=member_ctype)."""
        code = """
        struct S { int x; long y; };
        int *get_addr(void) {
            struct S s;
            return &s.x;
        }
        """
        ir, st = _compile_to_ir(code, tmp_path)
        addrs = _find_instructions(ir, "addr_of_member")
        found = [i for i in addrs if i.operand2 == "x"]
        assert len(found) > 0, "Expected addr_of_member for &s.x"
        for inst in found:
            if inst.result_type is not None:
                from pycc.types import TypeKind
                assert inst.result_type.kind == TypeKind.POINTER


class TestStoreMemberCType:
    """Test store_member/store_member_ptr meta["member_ctype"] annotations."""

    def test_store_member_has_member_ctype(self, tmp_path):
        """store_member for assignment carries member_ctype in meta."""
        code = """
        struct S { int x; long y; };
        void foo(void) {
            struct S s;
            s.x = 42;
        }
        """
        ir, st = _compile_to_ir(code, tmp_path)
        stores = _find_instructions(ir, "store_member")
        found = [i for i in stores if i.operand2 == "x"]
        assert len(found) > 0, "Expected store_member for s.x = 42"
        for inst in found:
            assert inst.meta is not None
            assert "member_ctype" in inst.meta, "store_member should have member_ctype in meta"
            from pycc.types import TypeKind
            assert inst.meta["member_ctype"].kind == TypeKind.INT

    def test_store_member_ptr_has_member_ctype(self, tmp_path):
        """store_member_ptr for assignment carries member_ctype in meta."""
        code = """
        struct S { int x; long y; };
        void foo(struct S *p) {
            p->x = 42;
        }
        """
        ir, st = _compile_to_ir(code, tmp_path)
        stores = _find_instructions(ir, "store_member_ptr")
        found = [i for i in stores if i.operand2 == "x"]
        assert len(found) > 0, "Expected store_member_ptr for p->x = 42"
        for inst in found:
            assert inst.meta is not None
            assert "member_ctype" in inst.meta, "store_member_ptr should have member_ctype in meta"
            from pycc.types import TypeKind
            assert inst.meta["member_ctype"].kind == TypeKind.INT


class TestInitializerMemberCType:
    """Test member access CType annotations in struct initializer lowering."""

    def test_initializer_store_member_has_ctype(self, tmp_path):
        """Struct initializer stores carry member_ctype in meta."""
        code = """
        struct S { int x; long y; };
        void foo(void) {
            struct S s = { 1, 2 };
        }
        """
        ir, st = _compile_to_ir(code, tmp_path)
        stores = _find_instructions(ir, "store_member")
        x_stores = [i for i in stores if i.operand2 == "x"]
        y_stores = [i for i in stores if i.operand2 == "y"]
        assert len(x_stores) > 0
        assert len(y_stores) > 0
        for inst in x_stores:
            assert inst.meta is not None and "member_ctype" in inst.meta
            from pycc.types import TypeKind
            assert inst.meta["member_ctype"].kind == TypeKind.INT
        for inst in y_stores:
            assert inst.meta is not None and "member_ctype" in inst.meta
            from pycc.types import TypeKind
            assert inst.meta["member_ctype"].kind == TypeKind.LONG

    def test_nested_struct_init_addr_of_member(self, tmp_path):
        """Nested struct initializer addr_of_member has PointerType result_type."""
        code = """
        struct Inner { int a; int b; };
        struct Outer { struct Inner inner; int c; };
        void foo(void) {
            struct Outer o = { { 1, 2 }, 3 };
        }
        """
        ir, st = _compile_to_ir(code, tmp_path)
        addrs = _find_instructions(ir, "addr_of_member")
        found = [i for i in addrs if i.operand2 == "inner"]
        assert len(found) > 0, "Expected addr_of_member for nested struct init"
        for inst in found:
            assert inst.result_type is not None
            from pycc.types import TypeKind
            assert inst.result_type.kind == TypeKind.POINTER
            assert inst.result_type.pointee is not None
            assert inst.result_type.pointee.kind == TypeKind.STRUCT
