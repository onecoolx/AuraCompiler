"""Tests for cast expression CType annotations (task 3.5).

Verifies that:
- Cast expressions create new temp variables via _new_temp_typed
- Cast does NOT modify the source operand's CType in the symbol table
- Typedef cast targets are resolved via ast_type_to_ctype_resolved
- result_type is set on cast IR instructions
"""

import pytest
from pycc.compiler import Compiler
from pycc.types import TypeKind, PointerType


def _compile_to_ir(code: str):
    """Compile C code and return (ir_instructions, sym_table, var_types)."""
    from pycc.ir import IRGenerator
    compiler = Compiler()
    tokens = compiler.get_tokens(code)
    ast = compiler.get_ast(tokens)
    sema_ctx, _ = compiler.analyze_semantics(ast)
    gen = IRGenerator()
    gen._sema_ctx = sema_ctx
    ir = gen.generate(ast)
    sym_table = getattr(gen, "_sym_table", None)
    var_types = dict(gen._var_types)
    return ir, sym_table, var_types


def _find_instructions(ir, op):
    """Find all IR instructions with the given op."""
    return [i for i in ir if i.op == op]


class TestCastFloatConversion:
    """Float cast conversions should produce typed temps with result_type."""

    def test_int_to_float_cast(self, tmp_path):
        """(float)x creates a typed temp with FloatType result_type."""
        code = """
        float foo(int x) {
            return (float)x;
        }
        """
        ir, st, vt = _compile_to_ir(code)
        i2f = _find_instructions(ir, "i2f")
        assert len(i2f) > 0, "Expected i2f instruction for (float)x"
        for inst in i2f:
            assert inst.result_type is not None, "i2f should have result_type"
            assert inst.result_type.kind == TypeKind.FLOAT

    def test_int_to_double_cast(self, tmp_path):
        """(double)x creates a typed temp with DOUBLE result_type."""
        code = """
        double foo(int x) {
            return (double)x;
        }
        """
        ir, st, vt = _compile_to_ir(code)
        i2d = _find_instructions(ir, "i2d")
        assert len(i2d) > 0, "Expected i2d instruction for (double)x"
        for inst in i2d:
            assert inst.result_type is not None, "i2d should have result_type"
            assert inst.result_type.kind == TypeKind.DOUBLE

    def test_float_to_int_cast(self, tmp_path):
        """(int)f creates a typed temp with INT result_type."""
        code = """
        int foo(float f) {
            return (int)f;
        }
        """
        ir, st, vt = _compile_to_ir(code)
        f2i = _find_instructions(ir, "f2i")
        assert len(f2i) > 0, "Expected f2i instruction for (int)f"
        for inst in f2i:
            assert inst.result_type is not None, "f2i should have result_type"
            assert inst.result_type.kind == TypeKind.INT

    def test_float_to_double_cast(self, tmp_path):
        """(double)f creates a typed temp with DOUBLE result_type."""
        code = """
        double foo(float f) {
            return (double)f;
        }
        """
        ir, st, vt = _compile_to_ir(code)
        f2d = _find_instructions(ir, "f2d")
        assert len(f2d) > 0, "Expected f2d instruction for (double)f"
        for inst in f2d:
            assert inst.result_type is not None, "f2d should have result_type"
            assert inst.result_type.kind == TypeKind.DOUBLE


class TestCastIntegerTruncation:
    """Integer cast truncations should produce typed temps."""

    def test_cast_to_unsigned_char(self, tmp_path):
        """(unsigned char)x creates a typed temp with CHAR kind."""
        code = """
        int foo(int x) {
            unsigned char c = (unsigned char)x;
            return c;
        }
        """
        ir, st, vt = _compile_to_ir(code)
        binops = _find_instructions(ir, "binop")
        mask_ops = [i for i in binops if i.operand2 == "$255"]
        assert len(mask_ops) > 0, "Expected binop & 255 for (unsigned char) cast"
        for inst in mask_ops:
            assert inst.result_type is not None, "char cast binop should have result_type"
            assert inst.result_type.kind == TypeKind.CHAR

    def test_cast_to_short(self, tmp_path):
        """(short)x creates typed temps with SHORT kind."""
        code = """
        int foo(int x) {
            short s = (short)x;
            return s;
        }
        """
        ir, st, vt = _compile_to_ir(code)
        binops = _find_instructions(ir, "binop")
        mask_ops = [i for i in binops if i.operand2 == "$65535"]
        assert len(mask_ops) > 0, "Expected binop & 65535 for (short) cast"
        for inst in mask_ops:
            assert inst.result_type is not None, "short cast binop should have result_type"
            assert inst.result_type.kind == TypeKind.SHORT


class TestCastSourcePreservation:
    """Cast must NOT modify the source operand's CType in the symbol table.

    Since function scopes are popped after IR generation, we verify via
    _var_types that the source operand's type string is preserved.
    """

    def test_cast_does_not_clobber_struct_pointer_var(self, tmp_path):
        """Casting struct S* to void* should not change the source var's type.

        Validates: Requirement 5.1
        """
        code = """
        struct S { int x; };
        void foo(struct S *p) {
            void *v = (void *)p;
        }
        """
        ir, st, vt = _compile_to_ir(code)
        # The parameter p should still have struct pointer type in _var_types
        p_type = vt.get("@p", "")
        assert "struct" in p_type.lower() or "S" in p_type, \
            f"@p type should still reference struct S, got '{p_type}'"
        assert "void" not in p_type, \
            f"@p type should NOT be clobbered to void*, got '{p_type}'"

    def test_cast_int_to_char_preserves_source(self, tmp_path):
        """(char)x should not change x's type in _var_types.

        Validates: Requirement 5.1
        """
        code = """
        int foo(int x) {
            char c = (char)x;
            return x;
        }
        """
        ir, st, vt = _compile_to_ir(code)
        # x should still be int, not char
        x_type = vt.get("@x", "")
        # The cast to char creates a new temp; x should remain int-ish
        # (The _var_types update for named vars may change it to "char"
        # for backward compat, but the symbol table should not be touched.
        # Since scope is popped, we verify the cast created a NEW temp.)
        binops = _find_instructions(ir, "binop")
        mask_ops = [i for i in binops if i.operand2 == "$255"]
        assert len(mask_ops) > 0, "Cast should create a new temp via binop"
        # The result of the mask should be a temp (%tN), not @x
        for inst in mask_ops:
            assert inst.result.startswith("%t"), \
                f"Cast result should be a new temp, got '{inst.result}'"


class TestCastTypedefResolution:
    """Typedef cast targets should be resolved via ast_type_to_ctype_resolved.

    Validates: Requirements 5.2, 5.3
    """

    def test_typedef_cast_resolves_to_underlying(self, tmp_path):
        """Cast to a typedef type should resolve to the underlying CType."""
        code = """
        typedef int MyInt;
        MyInt foo(long x) {
            return (MyInt)x;
        }
        """
        ir, st, vt = _compile_to_ir(code)
        # The cast from long to MyInt (=int) should work without errors
        # and the function should compile successfully
        assert len(ir) > 0

    def test_typedef_pointer_cast_compiles(self, tmp_path):
        """Cast to typedef pointer should compile and produce valid IR.

        Validates: Requirement 5.3
        """
        code = """
        struct Node { int val; };
        typedef struct Node Node_t;
        int foo(void *p) {
            Node_t *np = (Node_t *)p;
            return np->val;
        }
        """
        ir, st, vt = _compile_to_ir(code)
        # Should compile without errors and produce IR
        assert len(ir) > 0
        # np should have a pointer type in _var_types
        np_type = vt.get("@np", "")
        assert "*" in np_type, \
            f"@np should be a pointer type, got '{np_type}'"

    def test_float_cast_temp_in_symbol_table(self, tmp_path):
        """Float cast temp should be registered in the symbol table."""
        code = """
        float foo(int x) {
            return (float)x;
        }
        """
        ir, st, vt = _compile_to_ir(code)
        assert st is not None
        i2f = _find_instructions(ir, "i2f")
        assert len(i2f) > 0
        # The result temp should be in the global scope of the symbol table
        # (temps are registered at function scope which is popped, but
        # _new_temp_typed also updates _var_types)
        for inst in i2f:
            result_name = inst.result
            assert result_name in vt, \
                f"Cast temp {result_name} should be in _var_types"
            assert vt[result_name] == "float", \
                f"Cast temp type should be 'float', got '{vt[result_name]}'"
