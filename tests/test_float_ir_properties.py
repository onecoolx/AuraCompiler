"""Property tests: float IR generation correctness (Property 24)."""
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


def test_float_literal_generates_fmov():
    code = "int main(void) { float x = 3.14f; return 0; }\n"
    instrs = _gen_ir(code)
    fmovs = [i for i in instrs if i.op == "fmov"]
    assert len(fmovs) >= 1
    assert fmovs[0].meta and fmovs[0].meta.get("fp_type") == "float"


def test_double_literal_generates_fmov():
    code = "int main(void) { double y = 1.0; return 0; }\n"
    instrs = _gen_ir(code)
    fmovs = [i for i in instrs if i.op == "fmov"]
    assert len(fmovs) >= 1
    assert fmovs[0].meta and fmovs[0].meta.get("fp_type") == "double"
