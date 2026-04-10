"""Tests for long double IR type marking (Task 13.1).

Verifies that the IR generator correctly marks long double operations
with meta['fp_type'] = 'long double' and that _type_size returns 16.
"""
import pytest
from pycc.lexer import Lexer
from pycc.parser import Parser
from pycc.semantics import SemanticAnalyzer
from pycc.ir import IRGenerator, _type_size, _type_align


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


# --- _type_size / _type_align for long double ---

def test_type_size_long_double_string():
    assert _type_size("long double") == 16


def test_type_size_long_double_type_node():
    """Type node with base='long double' should return 16."""
    from pycc.ast_nodes import Type
    ty = Type(base="long double", line=0, column=0)
    assert _type_size(ty) == 16


def test_type_align_long_double_string():
    assert _type_align("long double") == 16


def test_type_align_long_double_type_node():
    from pycc.ast_nodes import Type
    ty = Type(base="long double", line=0, column=0)
    assert _type_align(ty) == 16


# --- Parser: long double type specifier ---

def test_parser_long_double_decl():
    """Parser should produce Type(base='long double') for 'long double x'."""
    code = "int main(void) { long double x; return 0; }\n"
    l = Lexer(code, "<test>")
    t = l.tokenize()
    p = Parser(t)
    ast = p.parse()
    # Find the declaration inside main's body
    fn = ast.declarations[0]
    body = fn.body
    # First statement should be the declaration
    decl = body.statements[0]
    assert decl.type.base == "long double"


# --- Float literal with L suffix ---

def test_long_double_literal_fmov():
    """Float literal with L suffix should generate fmov with fp_type='long double'."""
    code = "int main(void) { long double x = 3.14L; return 0; }\n"
    instrs = _gen_ir(code)
    fmovs = [i for i in instrs if i.op == "fmov"]
    assert len(fmovs) >= 1
    assert fmovs[0].meta and fmovs[0].meta.get("fp_type") == "long double"


# --- Binary operations with long double ---

def test_long_double_add():
    """Addition of two long double values should produce fadd with fp_type='long double'."""
    code = "int main(void) { long double a = 1.0L; long double b = 2.0L; long double c = a + b; return 0; }\n"
    instrs = _gen_ir(code)
    fadds = [i for i in instrs if i.op == "fadd"]
    assert len(fadds) >= 1
    assert fadds[0].meta and fadds[0].meta.get("fp_type") == "long double"


def test_long_double_sub():
    """Subtraction of long double values should produce fsub with fp_type='long double'."""
    code = "int main(void) { long double a = 3.0L; long double b = 1.0L; long double c = a - b; return 0; }\n"
    instrs = _gen_ir(code)
    fsubs = [i for i in instrs if i.op == "fsub"]
    assert len(fsubs) >= 1
    assert fsubs[0].meta and fsubs[0].meta.get("fp_type") == "long double"


def test_long_double_mul():
    """Multiplication of long double values should produce fmul with fp_type='long double'."""
    code = "int main(void) { long double a = 2.0L; long double b = 3.0L; long double c = a * b; return 0; }\n"
    instrs = _gen_ir(code)
    fmuls = [i for i in instrs if i.op == "fmul"]
    assert len(fmuls) >= 1
    assert fmuls[0].meta and fmuls[0].meta.get("fp_type") == "long double"


def test_long_double_div():
    """Division of long double values should produce fdiv with fp_type='long double'."""
    code = "int main(void) { long double a = 6.0L; long double b = 2.0L; long double c = a / b; return 0; }\n"
    instrs = _gen_ir(code)
    fdivs = [i for i in instrs if i.op == "fdiv"]
    assert len(fdivs) >= 1
    assert fdivs[0].meta and fdivs[0].meta.get("fp_type") == "long double"


def test_long_double_compare():
    """Comparison of long double values should produce fcmp with fp_type='long double'."""
    code = "int main(void) { long double a = 1.0L; long double b = 2.0L; int c = a < b; return 0; }\n"
    instrs = _gen_ir(code)
    fcmps = [i for i in instrs if i.op == "fcmp"]
    assert len(fcmps) >= 1
    assert fcmps[0].meta and fcmps[0].meta.get("fp_type") == "long double"


# --- Type promotion: long double > double > float ---

def test_long_double_promotes_double():
    """When mixing long double and double, result should be long double."""
    code = "int main(void) { long double a = 1.0L; double b = 2.0; long double c = a + b; return 0; }\n"
    instrs = _gen_ir(code)
    fadds = [i for i in instrs if i.op == "fadd"]
    assert len(fadds) >= 1
    assert fadds[0].meta and fadds[0].meta.get("fp_type") == "long double"


def test_long_double_promotes_int():
    """When mixing long double and int, result should be long double."""
    code = "int main(void) { long double a = 1.0L; int b = 2; long double c = a + b; return 0; }\n"
    instrs = _gen_ir(code)
    fadds = [i for i in instrs if i.op == "fadd"]
    assert len(fadds) >= 1
    assert fadds[0].meta and fadds[0].meta.get("fp_type") == "long double"
    # Should also have an i2ld conversion
    i2lds = [i for i in instrs if i.op == "i2ld"]
    assert len(i2lds) >= 1
    assert i2lds[0].meta and i2lds[0].meta.get("fp_type") == "long double"


# --- Cast operations ---

def test_cast_int_to_long_double():
    """Cast from int to long double should produce i2ld with fp_type='long double'."""
    code = "int main(void) { int x = 42; long double y = (long double)x; return 0; }\n"
    instrs = _gen_ir(code)
    i2lds = [i for i in instrs if i.op == "i2ld"]
    assert len(i2lds) >= 1
    assert i2lds[0].meta and i2lds[0].meta.get("fp_type") == "long double"


def test_cast_long_double_to_int():
    """Cast from long double to int should produce ld2i with fp_type='long double'."""
    code = "int main(void) { long double x = 3.14L; int y = (int)x; return 0; }\n"
    instrs = _gen_ir(code)
    ld2is = [i for i in instrs if i.op == "ld2i"]
    assert len(ld2is) >= 1
    assert ld2is[0].meta and ld2is[0].meta.get("fp_type") == "long double"


def test_cast_double_to_long_double():
    """Cast from double to long double should produce d2ld with fp_type='long double'."""
    code = "int main(void) { double x = 1.0; long double y = (long double)x; return 0; }\n"
    instrs = _gen_ir(code)
    d2lds = [i for i in instrs if i.op == "d2ld"]
    assert len(d2lds) >= 1
    assert d2lds[0].meta and d2lds[0].meta.get("fp_type") == "long double"


def test_cast_long_double_to_double():
    """Cast from long double to double should produce ld2d with fp_type='double'."""
    code = "int main(void) { long double x = 3.14L; double y = (double)x; return 0; }\n"
    instrs = _gen_ir(code)
    ld2ds = [i for i in instrs if i.op == "ld2d"]
    assert len(ld2ds) >= 1
    assert ld2ds[0].meta and ld2ds[0].meta.get("fp_type") == "double"


# --- Unary negation ---

def test_long_double_negation():
    """Unary negation of long double should produce fsub with fp_type='long double'."""
    code = "int main(void) { long double a = 1.0L; long double b = -a; return 0; }\n"
    instrs = _gen_ir(code)
    fsubs = [i for i in instrs if i.op == "fsub"]
    assert len(fsubs) >= 1
    assert fsubs[0].meta and fsubs[0].meta.get("fp_type") == "long double"


# --- sizeof(long double) ---

def test_sizeof_long_double():
    """sizeof(long double) should be 16."""
    code = "int main(void) { int x = sizeof(long double); return x; }\n"
    instrs = _gen_ir(code)
    # The sizeof should produce a $16 immediate
    movs = [i for i in instrs if i.op == "mov" and i.operand1 == "$16"]
    assert len(movs) >= 1
