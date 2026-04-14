"""Property-based tests for the GCC extension stripper.

**Validates: Requirements 3.1, 3.2, 3.4, 3.5, 3.6, 3.7, 3.8, 4.3**

Uses Hypothesis to verify that strip_gcc_extensions() correctly handles
arbitrary inputs containing GCC extensions while preserving non-extension text.
"""
from __future__ import annotations

import re
import string

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from pycc.gcc_extensions import strip_gcc_extensions


# ---------------------------------------------------------------------------
# Strategies (smart generators)
# ---------------------------------------------------------------------------

# Characters safe for C identifiers and simple expressions (no quotes, no
# backslashes, no GCC-extension prefixes).
_SAFE_C_CHARS = string.ascii_letters + string.digits + " \t\n;,{}()+-*/%=<>!&|^~?:."

# Strategy for "safe" C89 text that does NOT contain any GCC extension keywords.
# We filter out underscores entirely to avoid accidentally generating _Float or
# __attribute__ substrings.
_safe_c89_text = st.text(
    alphabet=st.sampled_from([c for c in _SAFE_C_CHARS if c != '_']),
    min_size=0,
    max_size=200,
)

# Strategy for text fragments that won't contain GCC keywords (allows underscores
# but avoids the specific patterns).
_context_text = st.text(
    alphabet=st.sampled_from(list(string.ascii_letters + string.digits + " \t\n;,{}=<>!&|^~?:.")),
    min_size=0,
    max_size=80,
)

# Strategy for balanced parenthesized content inside __attribute__((...)).
# Generates content with arbitrary nesting depth.
def _nested_parens_content(max_depth: int = 4) -> st.SearchStrategy[str]:
    """Generate content that can appear inside __attribute__((...)).

    May contain nested parentheses up to max_depth levels.
    """
    leaf = st.text(
        alphabet=st.sampled_from(list(string.ascii_letters + string.digits + " ,_")),
        min_size=0,
        max_size=20,
    )
    if max_depth <= 0:
        return leaf
    return st.one_of(
        leaf,
        _nested_parens_content(max_depth - 1).map(lambda s: f"({s})"),
        st.tuples(
            _nested_parens_content(max_depth - 1),
            leaf,
        ).map(lambda t: f"{t[0]}, {t[1]}"),
    )


# Strategy for a complete __attribute__((...)) annotation.
_attribute_annotation = _nested_parens_content(4).map(
    lambda content: f"__attribute__(({content}))"
)

# Simple GCC keywords to remove.
_SIMPLE_KW_LIST = ["__extension__", "__inline__", "__inline", "__restrict__", "__restrict"]
_simple_gcc_keyword = st.sampled_from(_SIMPLE_KW_LIST)

# _Float type mapping for verification.
_FLOAT_MAP = {
    "_Float128": "long double",
    "_Float64x": "long double",
    "_Float64":  "double",
    "_Float32x": "double",
    "_Float32":  "float",
}
_float_type = st.sampled_from(list(_FLOAT_MAP.keys()))


# ---------------------------------------------------------------------------
# Property 9: __attribute__ 嵌套括号移除
# Feature: parser-semantics-hardening, Property 9: __attribute__ nested paren removal
# ---------------------------------------------------------------------------

class TestAttributeNestedParenRemoval:
    """Property 9: __attribute__ 嵌套括号移除

    For any text containing __attribute__((...)) with arbitrary nesting depth,
    the output should not contain __attribute__ and non-attribute text should
    be preserved.

    **Validates: Requirements 3.1, 3.7**
    """

    @given(
        before=_context_text,
        attr=_attribute_annotation,
        after=_context_text,
    )
    @settings(max_examples=200, deadline=None)
    def test_attribute_removed_and_context_preserved(
        self, before: str, attr: str, after: str
    ):
        """__attribute__((...)) is removed; surrounding text is preserved.

        **Validates: Requirements 3.1, 3.7**
        """
        text = f"{before} {attr} {after}"
        result = strip_gcc_extensions(text)

        # The output must not contain __attribute__
        assert "__attribute__" not in result, (
            f"__attribute__ still present in output.\n"
            f"Input:  {text!r}\n"
            f"Output: {result!r}"
        )

        # The surrounding context text must be preserved (modulo whitespace
        # collapse from keyword removal producing spaces).
        # We check that before and after substrings appear in the result.
        if before.strip():
            assert before.strip() in result, (
                f"Context before attribute lost.\n"
                f"Expected substring: {before.strip()!r}\n"
                f"Output: {result!r}"
            )
        if after.strip():
            assert after.strip() in result, (
                f"Context after attribute lost.\n"
                f"Expected substring: {after.strip()!r}\n"
                f"Output: {result!r}"
            )

    @given(depth=st.integers(min_value=1, max_value=6))
    @settings(max_examples=100, deadline=None)
    def test_deep_nesting_removed(self, depth: int):
        """Deeply nested __attribute__ (3+ levels) is fully removed.

        **Validates: Requirements 3.7**
        """
        # Build nested content: (((...(x)...)))
        inner = "nonnull"
        for _ in range(depth):
            inner = f"({inner})"
        text = f"int x __attribute__(({inner}));"
        result = strip_gcc_extensions(text)

        assert "__attribute__" not in result
        assert "int x" in result
        assert ";" in result


# ---------------------------------------------------------------------------
# Property 10: 简单 GCC 关键字移除
# Feature: parser-semantics-hardening, Property 10: simple GCC keyword removal
# ---------------------------------------------------------------------------

class TestSimpleGccKeywordRemoval:
    """Property 10: 简单 GCC 关键字移除

    For any text containing __extension__, __inline, __inline__, __restrict,
    or __restrict__, the output should not contain these keywords and remaining
    text should be preserved.

    **Validates: Requirements 3.2, 3.4, 3.5**
    """

    @given(
        before=_context_text,
        keyword=_simple_gcc_keyword,
        after=_context_text,
    )
    @settings(max_examples=200, deadline=None)
    def test_keyword_removed_and_context_preserved(
        self, before: str, keyword: str, after: str
    ):
        """Simple GCC keyword is removed; surrounding text is preserved.

        **Validates: Requirements 3.2, 3.4, 3.5**
        """
        text = f"{before} {keyword} {after}"
        result = strip_gcc_extensions(text)

        # Build a regex that matches the keyword as a whole word.
        pattern = re.compile(r'(?<![a-zA-Z0-9_])' + re.escape(keyword) + r'(?![a-zA-Z0-9_])')
        assert not pattern.search(result), (
            f"Keyword {keyword!r} still present in output.\n"
            f"Input:  {text!r}\n"
            f"Output: {result!r}"
        )

        # Context text must be preserved.
        if before.strip():
            assert before.strip() in result, (
                f"Context before keyword lost.\n"
                f"Expected: {before.strip()!r}\nOutput: {result!r}"
            )
        if after.strip():
            assert after.strip() in result, (
                f"Context after keyword lost.\n"
                f"Expected: {after.strip()!r}\nOutput: {result!r}"
            )

    @given(
        keywords=st.lists(_simple_gcc_keyword, min_size=2, max_size=5),
    )
    @settings(max_examples=100, deadline=None)
    def test_multiple_keywords_all_removed(self, keywords: list[str]):
        """Multiple GCC keywords in one text are all removed.

        **Validates: Requirements 3.2, 3.4, 3.5**
        """
        text = " ".join(f"int {kw} x;" for kw in keywords)
        result = strip_gcc_extensions(text)

        for kw in _SIMPLE_KW_LIST:
            pattern = re.compile(r'(?<![a-zA-Z0-9_])' + re.escape(kw) + r'(?![a-zA-Z0-9_])')
            assert not pattern.search(result), (
                f"Keyword {kw!r} still present after stripping.\n"
                f"Input:  {text!r}\n"
                f"Output: {result!r}"
            )


# ---------------------------------------------------------------------------
# Property 11: Float 类型替换
# Feature: parser-semantics-hardening, Property 11: Float type replacement
# ---------------------------------------------------------------------------

class TestFloatTypeReplacement:
    """Property 11: Float 类型替换

    For any text containing _Float128, _Float64, _Float32, _Float64x, or
    _Float32x, they should be replaced with corresponding standard C types.

    **Validates: Requirements 3.6**
    """

    @given(
        before=_context_text,
        ftype=_float_type,
        after=_context_text,
    )
    @settings(max_examples=200, deadline=None)
    def test_float_type_replaced_correctly(
        self, before: str, ftype: str, after: str
    ):
        """_Float* type is replaced with the correct standard C type.

        **Validates: Requirements 3.6**
        """
        expected_replacement = _FLOAT_MAP[ftype]
        text = f"{before} {ftype} {after}"
        result = strip_gcc_extensions(text)

        # The original _Float* keyword should not appear as a whole word.
        pattern = re.compile(r'(?<![a-zA-Z0-9_])' + re.escape(ftype) + r'(?![a-zA-Z0-9_])')
        assert not pattern.search(result), (
            f"{ftype!r} still present in output.\n"
            f"Input:  {text!r}\n"
            f"Output: {result!r}"
        )

        # The replacement type should appear in the output.
        assert expected_replacement in result, (
            f"Expected replacement {expected_replacement!r} not found.\n"
            f"Input:  {text!r}\n"
            f"Output: {result!r}"
        )

        # Context text must be preserved.
        if before.strip():
            assert before.strip() in result, (
                f"Context before float type lost.\n"
                f"Expected: {before.strip()!r}\nOutput: {result!r}"
            )
        if after.strip():
            assert after.strip() in result, (
                f"Context after float type lost.\n"
                f"Expected: {after.strip()!r}\nOutput: {result!r}"
            )

    @given(
        ftypes=st.lists(_float_type, min_size=2, max_size=5),
    )
    @settings(max_examples=100, deadline=None)
    def test_multiple_float_types_all_replaced(self, ftypes: list[str]):
        """Multiple _Float* types in one text are all replaced.

        **Validates: Requirements 3.6**
        """
        text = " ".join(f"{ft} x{i};" for i, ft in enumerate(ftypes))
        result = strip_gcc_extensions(text)

        for ft in _FLOAT_MAP:
            pattern = re.compile(r'(?<![a-zA-Z0-9_])' + re.escape(ft) + r'(?![a-zA-Z0-9_])')
            assert not pattern.search(result), (
                f"{ft!r} still present after stripping.\n"
                f"Input:  {text!r}\n"
                f"Output: {result!r}"
            )


# ---------------------------------------------------------------------------
# Property 12: 非扩展文本恒等性
# Feature: parser-semantics-hardening, Property 12: non-extension text identity
# ---------------------------------------------------------------------------

class TestNonExtensionTextIdentity:
    """Property 12: 非扩展文本恒等性

    For any C89 text that does NOT contain any GCC extension keywords,
    strip_gcc_extensions(text) should return the input unchanged.

    **Validates: Requirements 3.8, 4.3**
    """

    @given(text=_safe_c89_text)
    @settings(max_examples=200, deadline=None)
    def test_safe_text_unchanged(self, text: str):
        """Text without GCC extensions passes through unchanged.

        **Validates: Requirements 3.8, 4.3**
        """
        result = strip_gcc_extensions(text)
        assert result == text, (
            f"Non-extension text was modified.\n"
            f"Input:  {text!r}\n"
            f"Output: {result!r}"
        )

    @given(text=st.text(
        alphabet=st.sampled_from(list(string.ascii_letters + string.digits + " \n\t;,{}()+-*/%=<>!&|^~?:.")),
        min_size=0,
        max_size=300,
    ))
    @settings(max_examples=200, deadline=None)
    def test_no_underscore_text_unchanged(self, text: str):
        """Text with no underscores at all is always unchanged.

        **Validates: Requirements 3.8, 4.3**
        """
        assume('_' not in text)
        result = strip_gcc_extensions(text)
        assert result == text

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_string_literals_with_fake_extensions_unchanged(self, data: st.DataObject):
        """String literals containing GCC-like keywords are not modified.

        **Validates: Requirements 3.8**
        """
        # Pick a GCC keyword to embed inside a string literal.
        keyword = data.draw(st.sampled_from(
            ["__attribute__", "__extension__", "__inline__", "__restrict__",
             "_Float128", "_Float64", "__asm__"]
        ))
        text = f'const char *s = "{keyword}";'
        result = strip_gcc_extensions(text)
        # The string literal content must be preserved exactly.
        assert f'"{keyword}"' in result, (
            f"String literal content was modified.\n"
            f"Input:  {text!r}\n"
            f"Output: {result!r}"
        )
