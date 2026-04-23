"""Property-based tests for macro expansion whitespace preservation.

**Validates: Requirements 13.1, 13.2**

Property 14: Macro expansion whitespace preservation roundtrip consistency
For any macro expansion result, re-lexing the output text should produce the
same token sequence as the expansion result (i.e. whitespace correctly separates
all tokens with no accidental token pasting).

Testing approach: use Hypothesis to generate random object-like macro
definitions with multiple tokens, expand them via the token-based
MacroExpander, serialize the result to text, re-tokenize, and verify
the token sequences match (ignoring whitespace tokens).
"""
from __future__ import annotations

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from pycc.preprocessor import MacroExpander, MacroDef, PPToken, PPTokenizer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_tokenizer = PPTokenizer()


def _non_space_tokens(tokens):
    """Extract non-space token texts from a token list."""
    return [t.text for t in tokens if t.kind != 'space']


def _serialize(tokens):
    """Serialize tokens to text, inserting spaces between adjacent non-space tokens."""
    parts = []
    prev_was_nonspace = False
    for t in tokens:
        if t.kind == 'space':
            parts.append(' ')
            prev_was_nonspace = False
        else:
            if prev_was_nonspace:
                parts.append(' ')
            parts.append(t.text)
            prev_was_nonspace = True
    return ''.join(parts)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

ident_text = st.text(
    alphabet=st.sampled_from(list("abcdefghijklmnopqrstuvwxyz")),
    min_size=1, max_size=5,
)

number_text = st.integers(min_value=0, max_value=999).map(str)

punct_text = st.sampled_from(['+', '-', '*', '/', '(', ')', ',', ';'])


@st.composite
def replacement_tokens(draw):
    """Generate a list of 1-5 tokens for a macro replacement list."""
    n = draw(st.integers(min_value=1, max_value=5))
    tokens = []
    for _ in range(n):
        kind = draw(st.sampled_from(['ident', 'number', 'punct']))
        if kind == 'ident':
            text = draw(ident_text)
        elif kind == 'number':
            text = draw(number_text)
        else:
            text = draw(punct_text)
        tokens.append(PPToken(kind, text))
        # Add space between tokens
        if draw(st.booleans()):
            tokens.append(PPToken('space', ' '))
    return tokens


# ---------------------------------------------------------------------------
# Property 14: Macro expansion whitespace preservation roundtrip consistency
# ---------------------------------------------------------------------------

class TestWhitespaceRoundtripProperties:
    """Property 14: Macro expansion whitespace preservation roundtrip consistency

    **Validates: Requirements 13.1, 13.2**
    """

    @given(repl=replacement_tokens())
    @settings(max_examples=100, deadline=None)
    def test_expansion_roundtrip_preserves_tokens(self, repl):
        """For any macro replacement list, expanding and re-tokenizing
        should produce the same non-space token sequence.

        This verifies that whitespace correctly separates all tokens
        and no accidental token pasting occurs.

        **Validates: Requirements 13.1, 13.2**
        """
        # Create a macro with the generated replacement
        macros = {
            'M': MacroDef(name='M', replacement=repl),
        }
        expander = MacroExpander(macros)

        # Expand
        result = expander.expand([PPToken('ident', 'M')])
        original_tokens = _non_space_tokens(result)

        # Serialize to text
        text = _serialize(result)

        # Re-tokenize
        retokenized = _tokenizer.tokenize(text)
        retokenized_tokens = _non_space_tokens(retokenized)

        # The non-space token sequences should match
        assert original_tokens == retokenized_tokens, (
            f"Token roundtrip mismatch:\n"
            f"  Original:    {original_tokens}\n"
            f"  Retokenized: {retokenized_tokens}\n"
            f"  Text: {text!r}\n"
            f"  Replacement: {[(t.kind, t.text) for t in repl]}"
        )

    @given(repl=replacement_tokens())
    @settings(max_examples=100, deadline=None)
    def test_serialized_output_has_no_accidental_pasting(self, repl):
        """When expansion result is serialized with proper spacing,
        re-tokenizing should not produce fewer tokens than the original
        (which would indicate accidental pasting).

        **Validates: Requirements 13.1**
        """
        macros = {
            'M': MacroDef(name='M', replacement=repl),
        }
        expander = MacroExpander(macros)
        result = expander.expand([PPToken('ident', 'M')])
        original_tokens = _non_space_tokens(result)

        # Serialize with proper spacing
        text = _serialize(result)

        # Re-tokenize
        retokenized = _tokenizer.tokenize(text)
        retokenized_tokens = _non_space_tokens(retokenized)

        # Should have same number of tokens (no accidental pasting)
        assert len(retokenized_tokens) == len(original_tokens), (
            f"Token count mismatch after serialization:\n"
            f"  Original ({len(original_tokens)}): {original_tokens}\n"
            f"  Retokenized ({len(retokenized_tokens)}): {retokenized_tokens}\n"
            f"  Text: {text!r}"
        )
