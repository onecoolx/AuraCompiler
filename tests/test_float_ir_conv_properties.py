"""Property tests: float type conversion IR (Property 25) and float function param/return IR (Property 26)."""
import pytest
from pycc.lexer import Lexer
from pycc.parser import Parser
from pycc.semantics import SemanticAnalyzer
from pycc.ir import IRGenerator


def _gen_ir(code: str):
    l = Lexer(code, "<test>")
    t = l.tokenize()
    p = Parser(t)
    ast = p.parse()
    sa = SemanticAnalyzer()
    ctx = sa.analyze(ast)
    irg = IRGenerator()
    irg._sema_ctx = ctx
    return irg.generate(ast)


def test_float_add_generates_fadd():
    code = "int main(void) { float a = 1.0f; float b = 2.0f; float c = a + b; return 0; }\n"
    instrs = _gen_ir(code)
    assert any(i.op == "fadd" for i in instrs)


def test_float_sub_generates_fsub():
    code = "int main(void) { float a = 3.0f; float b = 1.0f; float c = a - b; return 0; }\n"
    instrs = _gen_ir(code)
    assert any(i.op == "fsub" for i in instrs)


def test_float_mul_generates_fmul():
    code = "int main(void) { double a = 2.0; double b = 3.0; double c = a * b; return 0; }\n"
    instrs = _gen_ir(code)
    assert any(i.op == "fmul" for i in instrs)


def test_float_div_generates_fdiv():
    code = "int main(void) { double a = 6.0; double b = 2.0; double c = a / b; return 0; }\n"
    instrs = _gen_ir(code)
    assert any(i.op == "fdiv" for i in instrs)


def test_float_compare_generates_fcmp():
    code = "int main(void) { float a = 1.0f; float b = 2.0f; int r = a < b; return r; }\n"
    instrs = _gen_ir(code)
    assert any(i.op == "fcmp" for i in instrs)


def test_int_to_float_cast_generates_i2f():
    code = "int main(void) { int x = 42; float f = (float)x; return 0; }\n"
    instrs = _gen_ir(code)
    assert any(i.op == "i2f" for i in instrs)


def test_int_to_double_cast_generates_i2d():
    code = "int main(void) { int x = 42; double d = (double)x; return 0; }\n"
    instrs = _gen_ir(code)
    assert any(i.op == "i2d" for i in instrs)


def test_float_to_int_cast_generates_f2i():
    code = "int main(void) { float f = 3.14f; int x = (int)f; return x; }\n"
    instrs = _gen_ir(code)
    assert any(i.op == "f2i" for i in instrs)


def test_double_to_int_cast_generates_d2i():
    code = "int main(void) { double d = 3.14; int x = (int)d; return x; }\n"
    instrs = _gen_ir(code)
    assert any(i.op == "d2i" for i in instrs)


def test_float_to_double_cast_generates_f2d():
    code = "int main(void) { float f = 1.0f; double d = (double)f; return 0; }\n"
    instrs = _gen_ir(code)
    assert any(i.op == "f2d" for i in instrs)
