"""Property-based tests for # stringize operator escape correctness.

**Validates: Requirements 10.1, 10.2**

Property 12: 字符串化运算符转义正确性
For any 包含特殊字符（制表符、换行符、反斜杠、双引号）的宏参数，
# 字符串化运算符应在输出字符串中正确添加转义前缀，使结果为合法的 C 字符串字面量。

Testing approach: use Hypothesis to generate random token sequences containing
special characters, feed them to MacroExpander._stringize, and verify the
output is a valid C string literal (starts/ends with ", no unescaped special chars).
"""
from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from pycc.preprocessor import MacroExpander, PPToken


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_valid_c_string_literal(s: str) -> bool:
    """Check if s is a syntactically valid C string literal.

    Must start and end with unescaped double-quotes, and contain no
    unescaped double-quotes, tabs, or newlines inside.
    """
    if len(s) < 2 or s[0] != '"' or s[-1] != '"':
        return False
    inner = s[1:-1]
    i = 0
    while i < len(inner):
        ch = inner[i]
        if ch == '"':
            return False  # unescaped quote inside
        if ch == '\t' or ch == '\n':
            return False  # unescaped tab/newline
        if ch == '\\':
            i += 2  # skip escape sequence
            continue
        i += 1
    return True


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Characters that may appear in macro arguments
safe_chars = st.sampled_from(list("abcdefghijklmnopqrstuvwxyz0123456789_+-*/() "))
special_chars = st.sampled_from(['\t', '\n', '\\', '"'])
any_char = st.one_of(safe_chars, special_chars)

token_text = st.text(alphabet=any_char, min_size=1, max_size=10)


@st.composite
def token_sequence(draw):
    """Generate a list of PPTokens with random text including special chars."""
    n = draw(st.integers(min_value=1, max_value=5))
    tokens = []
    for _ in range(n):
        text = draw(token_text)
        # Classify: if it looks like a string literal, mark as 'string'
        if text.startswith('"') and text.endswith('"') and len(text) >= 2:
            kind = 'string'
        elif text.strip() == '':
            kind = 'space'
        else:
            kind = 'ident'
        tokens.append(PPToken(kind, text))
    return tokens


@st.composite
def ident_with_special_chars(draw):
    """Generate identifier-like tokens that contain special characters."""
    prefix = draw(st.text(alphabet=st.sampled_from(list("abcdefg")), min_size=1, max_size=3))
    special = draw(special_chars)
    suffix = draw(st.text(alphabet=st.sampled_from(list("hijklmn")), min_size=0, max_size=3))
    return [PPToken('ident', prefix + special + suffix)]


# ---------------------------------------------------------------------------
# Property 12: 字符串化运算符转义正确性
# ---------------------------------------------------------------------------

class TestStringizeEscapeProperties:
    """Property 12: 字符串化运算符转义正确性

    **Validates: Requirements 10.1, 10.2**
    """

    @given(tokens=token_sequence())
    @settings(max_examples=100, deadline=None)
    def test_stringize_produces_valid_c_string(self, tokens):
        """For any token sequence, _stringize should produce a valid C string literal.

        The result must start and end with double-quotes, and contain no
        unescaped special characters (tabs, newlines, double-quotes) inside.

        **Validates: Requirements 10.1, 10.2**
        """
        result = MacroExpander._stringize(tokens)

        # Must be a valid C string literal
        assert result.startswith('"'), f"Result should start with '\"': {result!r}"
        assert result.endswith('"'), f"Result should end with '\"': {result!r}"
        assert _is_valid_c_string_literal(result), (
            f"Result is not a valid C string literal: {result!r}\n"
            f"Input tokens: {[(t.kind, t.text) for t in tokens]}"
        )

    @given(tokens=ident_with_special_chars())
    @settings(max_examples=100, deadline=None)
    def test_stringize_escapes_special_chars_in_idents(self, tokens):
        """For any identifier containing special characters (tab, newline,
        backslash, double-quote), _stringize should escape them.

        **Validates: Requirements 10.1, 10.2**
        """
        result = MacroExpander._stringize(tokens)
        assert _is_valid_c_string_literal(result), (
            f"Result is not a valid C string literal: {result!r}\n"
            f"Input tokens: {[(t.kind, t.text) for t in tokens]}"
        )

    @given(n_spaces=st.integers(min_value=2, max_value=10))
    @settings(max_examples=50, deadline=None)
    def test_stringize_collapses_consecutive_whitespace(self, n_spaces):
        """Consecutive whitespace tokens should be collapsed to a single space.

        **Validates: Requirements 10.1**
        """
        tokens = [PPToken('ident', 'a')]
        for _ in range(n_spaces):
            tokens.append(PPToken('space', ' '))
        tokens.append(PPToken('ident', 'b'))

        result = MacroExpander._stringize(tokens)
        assert result == '"a b"', (
            f"Expected '\"a b\"' but got {result!r} for {n_spaces} spaces"
        )
