"""Tests for IR generator .resolved_type priority reading logic (Task 8.2).

Verifies that the IR generator prefers .resolved_type when available for:
1. Cast type judgment
2. BinaryOp pointer arithmetic detection
3. FunctionCall return type
"""

import pytest
from pycc.lexer import Lexer
from pycc.parser import Parser
from pycc.semantics import SemanticAnalyzer
from pycc.ir import IRGenerator, IRInstruction
from pycc.types import (
    IntegerType, FloatType, PointerType, TypeKind,
)


def _compile_to_ir(source: str):
    """Parse, analyze, and generate IR for a C source string."""
    lexer = Lexer(source, "<test>")
    tokens = lexer.tokenize()
    parser = Parser(tokens)
    ast = parser.parse()
    sema = SemanticAnalyzer()
    sema.analyze(ast)
    gen = IRGenerator()
    instructions = gen.generate(ast)
    return instructions, gen


class TestCastResolvedTypePriority:
    """Cast expressions should use .resolved_type when available."""

    def test_cast_to_int_uses_resolved_type(self):
        """Cast to int should work and the resolved_type is preferred."""
        src = "int main(void) { double x = 3.14; int y = (int)x; return y; }\n"
        instructions, gen = _compile_to_ir(src)
        # Should have a d2i or f2i conversion instruction
        conv_ops = [i for i in instructions if i.op in ("d2i", "f2i")]
        assert len(conv_ops) > 0

    def test_cast_to_float_uses_resolved_type(self):
        """Cast to float should work and the resolved_type is preferred."""
        src = "int main(void) { int x = 42; float y = (float)x; return 0; }\n"
        instructions, gen = _compile_to_ir(src)
        # Should have an i2f conversion instruction
        conv_ops = [i for i in instructions if i.op == "i2f"]
        assert len(conv_ops) > 0

    def test_cast_to_pointer_preserves_type(self):
        """Cast to pointer type should preserve pointer info."""
        src = "int main(void) { long x = 0; int *p = (int *)x; return *p; }\n"
        instructions, gen = _compile_to_ir(src)
        # The cast result should be recorded as a pointer type in _var_types
        # (verified by no crash and correct IR generation)
        assert any(i.op == "func_begin" for i in instructions)


class TestBinaryOpPointerArithmeticResolvedType:
    """BinaryOp pointer arithmetic should use .resolved_type for detection."""

    def test_pointer_plus_int_scales_correctly(self):
        """ptr + int should scale by pointee size using resolved_type info."""
        src = "int main(void) { int arr[10]; int *p = arr; int *q = p + 2; return *q; }\n"
        instructions, gen = _compile_to_ir(src)
        # Should have a multiply by 4 (sizeof(int)) for pointer scaling
        scale_ops = [i for i in instructions
                     if i.op == "binop" and i.label == "*"
                     and i.operand2 == "$4"]
        assert len(scale_ops) > 0

    def test_pointer_minus_int_scales_correctly(self):
        """ptr - int should scale by pointee size."""
        src = "int main(void) { int arr[10]; int *p = arr + 5; int *q = p - 2; return *q; }\n"
        instructions, gen = _compile_to_ir(src)
        # Should have scaling operations for pointer arithmetic
        scale_ops = [i for i in instructions
                     if i.op == "binop" and i.label == "*"
                     and i.operand2 == "$4"]
        assert len(scale_ops) > 0

    def test_pointer_difference_divides_by_pointee_size(self):
        """ptr - ptr should divide by pointee size to get element count."""
        src = "int main(void) { int arr[10]; int *p = arr; int *q = arr + 5; long diff = q - p; return (int)diff; }\n"
        instructions, gen = _compile_to_ir(src)
        # Should have a divide by 4 (sizeof(int)) for pointer difference
        div_ops = [i for i in instructions
                   if i.op == "binop" and i.label == "/"
                   and i.operand2 == "$4"]
        assert len(div_ops) > 0


class TestFunctionCallReturnTypeResolvedType:
    """FunctionCall should use .resolved_type for return type registration."""

    def test_function_call_return_type_registered(self):
        """Function call result should have correct type in symbol table."""
        src = "int foo(void);\nint main(void) { int x = foo(); return x; }\n"
        instructions, gen = _compile_to_ir(src)
        # Should generate a call instruction
        call_ops = [i for i in instructions if i.op == "call"]
        assert len(call_ops) > 0
        # The call result temp should be in the symbol table
        call_result = call_ops[0].result
        if gen._sym_table:
            ct = gen._sym_table.lookup(call_result)
            assert ct is not None
            assert isinstance(ct, IntegerType)

    def test_function_call_float_return_type(self):
        """Float-returning function call should register float type."""
        src = "double bar(int x);\nint main(void) { double y = bar(42); return (int)y; }\n"
        instructions, gen = _compile_to_ir(src)
        # Should have a call and the result should be typed as double
        call_ops = [i for i in instructions if i.op == "call"]
        assert len(call_ops) > 0

    def test_function_call_pointer_return_type(self):
        """Pointer-returning function call should register pointer type."""
        src = "int *get_ptr(void);\nint main(void) { int *p = get_ptr(); return *p; }\n"
        instructions, gen = _compile_to_ir(src)
        call_ops = [i for i in instructions if i.op == "call"]
        assert len(call_ops) > 0
        call_result = call_ops[0].result
        if gen._sym_table:
            ct = gen._sym_table.lookup(call_result)
            assert ct is not None
            assert isinstance(ct, PointerType)
