"""Tests for array member access via pointer/dot, function pointer dereference
detection, and unsigned division codegen.

These tests verify three fixes:
1. p->arr[i] and s.arr[i] where arr is an array member must emit
   addr_of_member_ptr (array-to-pointer decay) instead of load_member_ptr.
2. _is_function_pointer_operand must detect typedef function pointers
   loaded via load_member_ptr (e.g. g->frealloc).
3. Division of unsigned operands (including typedef like size_t) must use
   unsigned div instruction, not signed idiv.
"""

import pytest
from pycc.compiler import Compiler


def _compile_to_asm(code: str) -> str:
    """Compile C code to assembly, raising on errors."""
    c = Compiler()
    result = c.compile_code(code)
    assert not result.errors, f"Compilation errors: {result.errors}"
    return result.assembly


class TestArrayMemberAccess:
    """Array members accessed via -> or . must decay to pointer (address)."""

    def test_pointer_arrow_byte_array_store(self):
        """p->arr[i] = val where arr is unsigned char[] must use movb."""
        code = '''
typedef unsigned char lu_byte;
struct S {
    long x;
    lu_byte data[6];
};
void test(struct S *p) {
    p->data[3] = 42;
}
'''
        asm = _compile_to_asm(code)
        # Must use byte store (movb), not 4-byte store (movl)
        assert "movb" in asm
        # Must NOT use imulq $4 (wrong element size)
        assert "imulq $4" not in asm

    def test_pointer_arrow_int_array_store(self):
        """p->arr[i] = val where arr is int[] must use movl with imulq $4."""
        code = '''
struct S {
    long x;
    int data[10];
};
void test(struct S *p) {
    p->data[2] = 99;
}
'''
        asm = _compile_to_asm(code)
        # Must use 4-byte store
        assert "movl" in asm
        assert "imulq $4" in asm

    def test_pointer_arrow_byte_array_load(self):
        """val = p->arr[i] where arr is unsigned char[] must load 1 byte."""
        code = '''
typedef unsigned char lu_byte;
struct S {
    long x;
    lu_byte data[6];
};
lu_byte test(struct S *p) {
    return p->data[3];
}
'''
        asm = _compile_to_asm(code)
        # The addr_of_member_ptr should compute the array address correctly
        # (addq $8 for offset of data member)
        assert "addq $8" in asm

    def test_dot_access_array_member(self):
        """s.arr[i] where arr is an array member must also decay to pointer."""
        code = '''
struct S {
    int x;
    int data[4];
};
int test(void) {
    struct S s;
    s.data[1] = 77;
    return s.data[1];
}
'''
        asm = _compile_to_asm(code)
        # Should compile without errors and use correct element size
        assert "imulq $4" in asm


class TestFunctionPointerDereference:
    """Dereferencing a function pointer typedef via struct member must be no-op."""

    def test_fptr_typedef_member_deref(self):
        """(*g->frealloc)(...) must not dereference the function pointer."""
        code = '''
typedef void * (*Alloc)(void *ud, void *ptr, unsigned long os, unsigned long ns);
struct GS {
    Alloc frealloc;
    void *ud;
};
void *test(struct GS *g, unsigned long tag, unsigned long size) {
    return (*g->frealloc)(g->ud, (void*)0, tag, size);
}
'''
        asm = _compile_to_asm(code)
        # The function pointer should be loaded once and called directly.
        # There must NOT be a movslq (%rax),%rax pattern (spurious deref).
        assert "movslq (%rax), %rax" not in asm
        # Must have call *%rax (indirect call)
        assert "call *%rax" in asm


class TestUnsignedDivision:
    """Division with unsigned operands must use unsigned div instruction."""

    def test_size_t_division(self):
        """size_t / int must use divq, not idivq."""
        code = '''
typedef unsigned long size_t;
unsigned long test(void) {
    size_t max_sizet = ~(size_t)0;
    return max_sizet / 9;
}
'''
        asm = _compile_to_asm(code)
        assert "divq" in asm
        assert "idivq" not in asm

    def test_unsigned_long_division(self):
        """unsigned long / unsigned long must use divq."""
        code = '''
unsigned long test(unsigned long a, unsigned long b) {
    return a / b;
}
'''
        asm = _compile_to_asm(code)
        assert "divq" in asm
        assert "idivq" not in asm

    def test_signed_division_unchanged(self):
        """int / int must still use idivq."""
        code = '''
int test(int a, int b) {
    return a / b;
}
'''
        asm = _compile_to_asm(code)
        assert "idivq" in asm

    def test_unsigned_modulo(self):
        """unsigned long % unsigned long must use divq."""
        code = '''
unsigned long test(unsigned long a, unsigned long b) {
    return a % b;
}
'''
        asm = _compile_to_asm(code)
        assert "divq" in asm
        assert "idivq" not in asm
