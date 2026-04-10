"""Property-based tests for long double conversion roundtrip consistency.

**Validates: Requirements 14.3**

Property 15: long double 转换往返一致性
For any 可精确表示为 double 的浮点值，将其转换为 long double 再转换回 double
应产生与原始值相等的结果。

Testing approach: use Hypothesis to generate double-representable float values,
verify that the IR generator produces correct d2ld and ld2d conversion ops
with proper fp_type metadata, ensuring the roundtrip is semantically correct.
"""
from __future__ import annotations

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from pycc.lexer import Lexer
from pycc.parser import Parser
from pycc.semantics import SemanticAnalyzer
from pycc.ir import IRGenerator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Generate double-representable float values (avoid NaN, Inf, subnormals)
double_values = st.floats(
    min_value=-1e15, max_value=1e15,
    allow_nan=False, allow_infinity=False,
    allow_subnormal=False,
)

# Small integer values that are exactly representable as double
exact_int_values = st.integers(min_value=-1000000, max_value=1000000)


# ---------------------------------------------------------------------------
# Property 15: long double 转换往返一致性
# ---------------------------------------------------------------------------

class TestLongDoubleRoundtripProperties:
    """Property 15: long double 转换往返一致性

    **Validates: Requirements 14.3**
    """

    @given(val=exact_int_values)
    @settings(max_examples=100, deadline=None)
    def test_int_to_ld_to_int_roundtrip_ir(self, val):
        """For any integer value, int -> long double -> int roundtrip should
        produce correct IR conversion ops (i2ld then ld2i).

        **Validates: Requirements 14.3**
        """
        code = f"""
int main(void) {{
    int x = {val};
    long double ld = (long double)x;
    int y = (int)ld;
    return 0;
}}
"""
        instrs = _gen_ir(code)

        # Should have i2ld conversion
        i2lds = [i for i in instrs if i.op == "i2ld"]
        assert len(i2lds) >= 1, f"Expected i2ld for int->long double conversion, val={val}"
        assert i2lds[0].meta.get("fp_type") == "long double"

        # Should have ld2i conversion
        ld2is = [i for i in instrs if i.op == "ld2i"]
        assert len(ld2is) >= 1, f"Expected ld2i for long double->int conversion, val={val}"
        assert ld2is[0].meta.get("fp_type") == "long double"

    @given(val=double_values)
    @settings(max_examples=100, deadline=None)
    def test_double_to_ld_to_double_roundtrip_ir(self, val):
        """For any double-representable float value, double -> long double -> double
        roundtrip should produce correct IR conversion ops (d2ld then ld2d).

        **Validates: Requirements 14.3**
        """
        # Format the value as a C double literal
        code = f"""
int main(void) {{
    double x = {val};
    long double ld = (long double)x;
    double y = (double)ld;
    return 0;
}}
"""
        instrs = _gen_ir(code)

        # Should have d2ld conversion
        d2lds = [i for i in instrs if i.op == "d2ld"]
        assert len(d2lds) >= 1, f"Expected d2ld for double->long double conversion, val={val}"
        assert d2lds[0].meta.get("fp_type") == "long double"

        # Should have ld2d conversion
        ld2ds = [i for i in instrs if i.op == "ld2d"]
        assert len(ld2ds) >= 1, f"Expected ld2d for long double->double conversion, val={val}"

    @given(val=exact_int_values)
    @settings(max_examples=100, deadline=None)
    def test_long_double_arithmetic_ir_marking(self, val):
        """For any integer value used in long double arithmetic, the IR should
        mark operations with fp_type='long double'.

        **Validates: Requirements 14.3**
        """
        code = f"""
int main(void) {{
    long double a = {val}.0L;
    long double b = 1.0L;
    long double c = a + b;
    return 0;
}}
"""
        instrs = _gen_ir(code)

        # Should have fadd with fp_type='long double'
        fadds = [i for i in instrs if i.op == "fadd"]
        assert len(fadds) >= 1, f"Expected fadd for long double addition, val={val}"
        assert fadds[0].meta.get("fp_type") == "long double"
