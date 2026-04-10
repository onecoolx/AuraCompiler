"""Property-based tests for #if integer evaluation consistency.

**Validates: Requirements 12.1, 12.2**

Property 13: #if 整数求值一致性
For any #if 表达式中的整数运算（包括带后缀的字面量和溢出情况），预处理器应按照
选定的一致策略（Python 任意精度）求值，且相同表达式在不同上下文中产生相同结果。

Testing approach: use Hypothesis to generate random #if integer expressions,
evaluate them both via Python and via the preprocessor, and verify consistency.
"""
from __future__ import annotations

import textwrap
from pathlib import Path

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from pycc.preprocessor import Preprocessor


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pp_eval(tmp_path, expr: str) -> bool:
    """Evaluate a #if expression via the preprocessor. Returns True/False."""
    code = f"#if {expr}\nYES\n#else\nNO\n#endif\n"
    src = tmp_path / "t.c"
    src.write_text(code, encoding="utf-8")
    pp = Preprocessor(include_paths=[])
    result = pp.preprocess(str(src))
    return "YES" in result.text


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

small_int = st.integers(min_value=0, max_value=1000)
nonzero_int = st.integers(min_value=1, max_value=100)
suffix = st.sampled_from(["", "L", "U", "UL", "l", "u", "ul", "LL", "ULL"])

@st.composite
def suffixed_literal(draw):
    """Generate an integer literal with optional suffix."""
    val = draw(small_int)
    sfx = draw(suffix)
    return f"{val}{sfx}", val

@st.composite
def binary_add_expr(draw):
    """Generate a + b expression with expected result."""
    a = draw(small_int)
    b = draw(small_int)
    sa = draw(suffix)
    sb = draw(suffix)
    return f"{a}{sa} + {b}{sb}", a + b

@st.composite
def binary_mul_expr(draw):
    """Generate a * b expression with expected result."""
    a = draw(st.integers(min_value=0, max_value=100))
    b = draw(st.integers(min_value=0, max_value=100))
    return f"{a} * {b}", a * b

@st.composite
def comparison_expr(draw):
    """Generate a comparison expression with expected result."""
    a = draw(small_int)
    b = draw(small_int)
    op = draw(st.sampled_from(["==", "!=", "<", ">", "<=", ">="]))
    expected = eval(f"{a} {op} {b}")
    return f"{a} {op} {b}", bool(expected)


# ---------------------------------------------------------------------------
# Property 13: #if 整数求值一致性
# ---------------------------------------------------------------------------

class TestIfEvalProperties:
    """Property 13: #if 整数求值一致性

    **Validates: Requirements 12.1, 12.2**
    """

    @given(data=suffixed_literal())
    @settings(max_examples=100, deadline=None)
    def test_suffixed_literal_evaluates_correctly(self, tmp_path_factory, data):
        """Integer literals with suffixes (L, U, UL, etc.) should evaluate
        to the correct numeric value.

        **Validates: Requirements 12.2**
        """
        expr, expected_val = data
        tmp_path = tmp_path_factory.mktemp("test")
        # Test: #if <literal> == <expected_val>
        result = _pp_eval(tmp_path, f"{expr} == {expected_val}")
        assert result, (
            f"Expected {expr} == {expected_val} to be true, but preprocessor "
            f"evaluated it as false"
        )

    @given(data=binary_add_expr())
    @settings(max_examples=100, deadline=None)
    def test_addition_consistent(self, tmp_path_factory, data):
        """a + b should produce the same result as Python addition.

        **Validates: Requirements 12.1**
        """
        expr, expected = data
        tmp_path = tmp_path_factory.mktemp("test")
        result = _pp_eval(tmp_path, f"({expr}) == {expected}")
        assert result, (
            f"Expected ({expr}) == {expected} to be true"
        )

    @given(data=binary_mul_expr())
    @settings(max_examples=100, deadline=None)
    def test_multiplication_consistent(self, tmp_path_factory, data):
        """a * b should produce the same result as Python multiplication.

        **Validates: Requirements 12.1**
        """
        expr, expected = data
        tmp_path = tmp_path_factory.mktemp("test")
        result = _pp_eval(tmp_path, f"({expr}) == {expected}")
        assert result, (
            f"Expected ({expr}) == {expected} to be true"
        )

    @given(data=comparison_expr())
    @settings(max_examples=100, deadline=None)
    def test_comparison_consistent(self, tmp_path_factory, data):
        """Comparison operators should produce consistent results.

        **Validates: Requirements 12.1**
        """
        expr, expected = data
        tmp_path = tmp_path_factory.mktemp("test")
        result = _pp_eval(tmp_path, expr)
        assert result == expected, (
            f"Expected #if {expr} to be {expected}, got {result}"
        )

    @given(
        a=small_int,
        b=nonzero_int,
    )
    @settings(max_examples=50, deadline=None)
    def test_same_expr_same_result_in_different_contexts(self, tmp_path_factory, a, b):
        """Same expression evaluated in two different #if contexts should
        produce the same result (consistency).

        **Validates: Requirements 12.1**
        """
        tmp_path = tmp_path_factory.mktemp("test")
        expr = f"{a} + {b}"
        expected = a + b

        code = f"""#if ({expr}) == {expected}
FIRST
#endif
#if ({expr}) == {expected}
SECOND
#endif
"""
        src = tmp_path / "t.c"
        src.write_text(code, encoding="utf-8")
        pp = Preprocessor(include_paths=[])
        result = pp.preprocess(str(src))
        assert "FIRST" in result.text and "SECOND" in result.text, (
            f"Same expression ({expr}) should produce same result in both contexts"
        )
