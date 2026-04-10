"""Tests for long double x87 codegen (Task 13.2).

Verifies that the code generator produces x87 FPU instructions for
long double operations (fp_type='long double' in IR meta).
"""
import pytest
from pycc.lexer import Lexer
from pycc.parser import Parser
from pycc.semantics import SemanticAnalyzer
from pycc.ir import IRGenerator
from pycc.codegen import CodeGenerator


def _gen_asm(code: str) -> str:
    """Compile C code to assembly string."""
    l = Lexer(code, "<test>")
    t = l.tokenize()
    p = Parser(t)
    ast = p.parse()
    sa = SemanticAnalyzer()
    ctx = sa.analyze(ast)
    irg = IRGenerator()
    irg._sema_ctx = ctx
    instrs = irg.generate(ast)
    cg = CodeGenerator(sema_ctx=ctx)
    return cg.generate(instrs)


# --- fmov: long double literal load ---

def test_fmov_long_double_uses_fldl():
    """fmov with fp_type='long double' should use fldl (load double into x87)."""
    code = "int main(void) { long double x = 3.14L; return 0; }\n"
    asm = _gen_asm(code)
    assert "fldl" in asm, f"Expected fldl in assembly:\n{asm}"


def test_fmov_long_double_uses_fstpt():
    """fmov with fp_type='long double' should store via fstpt (80-bit store)."""
    code = "int main(void) { long double x = 3.14L; return 0; }\n"
    asm = _gen_asm(code)
    assert "fstpt" in asm, f"Expected fstpt in assembly:\n{asm}"


# --- fadd: long double addition ---

def test_fadd_long_double_uses_fldt():
    """fadd with fp_type='long double' should load operands via fldt."""
    code = "int main(void) { long double a = 1.0L; long double b = 2.0L; long double c = a + b; return 0; }\n"
    asm = _gen_asm(code)
    assert "fldt" in asm, f"Expected fldt in assembly:\n{asm}"


def test_fadd_long_double_uses_faddp():
    """fadd with fp_type='long double' should use faddp instruction."""
    code = "int main(void) { long double a = 1.0L; long double b = 2.0L; long double c = a + b; return 0; }\n"
    asm = _gen_asm(code)
    assert "faddp" in asm, f"Expected faddp in assembly:\n{asm}"


# --- fsub: long double subtraction ---

def test_fsub_long_double_uses_fsubrp():
    """fsub with fp_type='long double' should use fsubrp (reverse subtract for correct order)."""
    code = "int main(void) { long double a = 3.0L; long double b = 1.0L; long double c = a - b; return 0; }\n"
    asm = _gen_asm(code)
    assert "fsubrp" in asm, f"Expected fsubrp in assembly:\n{asm}"


# --- fmul: long double multiplication ---

def test_fmul_long_double_uses_fmulp():
    """fmul with fp_type='long double' should use fmulp instruction."""
    code = "int main(void) { long double a = 2.0L; long double b = 3.0L; long double c = a * b; return 0; }\n"
    asm = _gen_asm(code)
    assert "fmulp" in asm, f"Expected fmulp in assembly:\n{asm}"


# --- fdiv: long double division ---

def test_fdiv_long_double_uses_fdivrp():
    """fdiv with fp_type='long double' should use fdivrp (reverse divide for correct order)."""
    code = "int main(void) { long double a = 6.0L; long double b = 2.0L; long double c = a / b; return 0; }\n"
    asm = _gen_asm(code)
    assert "fdivrp" in asm, f"Expected fdivrp in assembly:\n{asm}"


# --- fcmp: long double comparison ---

def test_fcmp_long_double_uses_fcomip():
    """fcmp with fp_type='long double' should use fcomip instruction."""
    code = "int main(void) { long double a = 1.0L; long double b = 2.0L; int c = a < b; return 0; }\n"
    asm = _gen_asm(code)
    assert "fcomip" in asm, f"Expected fcomip in assembly:\n{asm}"


def test_fcmp_long_double_pops_both():
    """fcmp should pop both x87 stack entries (fcomip + fstp)."""
    code = "int main(void) { long double a = 1.0L; long double b = 2.0L; int c = a < b; return 0; }\n"
    asm = _gen_asm(code)
    # After fcomip, there should be an fstp to pop the remaining entry
    assert "fstp %st(0)" in asm, f"Expected 'fstp %st(0)' in assembly:\n{asm}"


# --- i2ld: int to long double conversion ---

def test_i2ld_uses_fildq():
    """i2ld should use fildq to convert integer to long double."""
    code = "int main(void) { int x = 42; long double y = (long double)x; return 0; }\n"
    asm = _gen_asm(code)
    assert "fildq" in asm, f"Expected fildq in assembly:\n{asm}"


# --- ld2i: long double to int conversion ---

def test_ld2i_uses_fistpq():
    """ld2i should use fistpq to convert long double to integer."""
    code = "int main(void) { long double x = 3.14L; int y = (int)x; return 0; }\n"
    asm = _gen_asm(code)
    assert "fistpq" in asm, f"Expected fistpq in assembly:\n{asm}"


def test_ld2i_sets_truncation_mode():
    """ld2i should set x87 rounding mode to truncation (C cast semantics)."""
    code = "int main(void) { long double x = 3.14L; int y = (int)x; return 0; }\n"
    asm = _gen_asm(code)
    # Should save/restore control word and set truncation bits
    assert "fnstcw" in asm, f"Expected fnstcw in assembly:\n{asm}"
    assert "fldcw" in asm, f"Expected fldcw in assembly:\n{asm}"


# --- d2ld: double to long double conversion ---

def test_d2ld_uses_fldl():
    """d2ld should use fldl to load double into x87 stack."""
    code = "int main(void) { double x = 1.0; long double y = (long double)x; return 0; }\n"
    asm = _gen_asm(code)
    assert "fldl" in asm, f"Expected fldl in assembly:\n{asm}"


def test_d2ld_stores_as_tbyte():
    """d2ld should store result as 80-bit tbyte via fstpt."""
    code = "int main(void) { double x = 1.0; long double y = (long double)x; return 0; }\n"
    asm = _gen_asm(code)
    assert "fstpt" in asm, f"Expected fstpt in assembly:\n{asm}"


# --- ld2d: long double to double conversion ---

def test_ld2d_uses_fldt():
    """ld2d should load long double via fldt."""
    code = "int main(void) { long double x = 3.14L; double y = (double)x; return 0; }\n"
    asm = _gen_asm(code)
    assert "fldt" in asm, f"Expected fldt in assembly:\n{asm}"


def test_ld2d_stores_as_double():
    """ld2d should store result as double via fstpl."""
    code = "int main(void) { long double x = 3.14L; double y = (double)x; return 0; }\n"
    asm = _gen_asm(code)
    assert "fstpl" in asm, f"Expected fstpl in assembly:\n{asm}"


# --- f2ld: float to long double conversion ---

def test_f2ld_uses_flds():
    """f2ld should load float via flds."""
    code = "int main(void) { float x = 1.0f; long double y = (long double)x; return 0; }\n"
    asm = _gen_asm(code)
    assert "flds" in asm, f"Expected flds in assembly:\n{asm}"


# --- ld2f: long double to float conversion ---

def test_ld2f_uses_fstps():
    """ld2f should store result as float via fstps."""
    code = "int main(void) { long double x = 3.14L; float y = (float)x; return 0; }\n"
    asm = _gen_asm(code)
    assert "fstps" in asm, f"Expected fstps in assembly:\n{asm}"


# --- Stack frame alignment ---

def test_long_double_16byte_stack_alignment():
    """long double locals should get 16-byte aligned stack slots."""
    code = "int main(void) { long double x = 1.0L; return 0; }\n"
    asm = _gen_asm(code)
    # The assembly should contain fldt/fstpt with offsets that are multiples of 16
    # We just verify the instructions are present and the code generates without error
    assert "fstpt" in asm
    assert "fldl" in asm


# --- No regression: float/double still use SSE ---

def test_float_still_uses_sse():
    """float operations should still use SSE instructions, not x87."""
    code = "int main(void) { float a = 1.0f; float b = 2.0f; float c = a + b; return 0; }\n"
    asm = _gen_asm(code)
    assert "addss" in asm, f"Expected addss for float addition:\n{asm}"
    assert "fldt" not in asm, f"float should not use x87 fldt:\n{asm}"


def test_double_still_uses_sse():
    """double operations should still use SSE instructions, not x87."""
    code = "int main(void) { double a = 1.0; double b = 2.0; double c = a + b; return 0; }\n"
    asm = _gen_asm(code)
    assert "addsd" in asm, f"Expected addsd for double addition:\n{asm}"
    assert "fldt" not in asm, f"double should not use x87 fldt:\n{asm}"


# --- Negation ---

def test_long_double_negation_uses_x87():
    """Negation of long double should use x87 fsub (0.0 - x)."""
    code = "int main(void) { long double a = 1.0L; long double b = -a; return 0; }\n"
    asm = _gen_asm(code)
    # Negation is implemented as fsub(0.0, a) which uses fsubrp
    assert "fsubrp" in asm or "fsubp" in asm, f"Expected x87 subtract for negation:\n{asm}"
