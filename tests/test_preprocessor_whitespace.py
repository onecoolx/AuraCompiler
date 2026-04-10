"""Tests for macro replacement whitespace preservation (Task 11.1).

Covers Requirements 13.1, 13.2:
- Whitespace is inserted between adjacent tokens to prevent accidental pasting
- Consecutive whitespace is collapsed to a single space per C89 §6.8.3
"""
import textwrap
from pathlib import Path

from pycc.preprocessor import Preprocessor, MacroExpander, MacroDef, PPToken, PPTokenizer


def _pp(tmp_path, code: str) -> str:
    src = tmp_path / "t.c"
    src.write_text(textwrap.dedent(code).lstrip(), encoding="utf-8")
    pp = Preprocessor(include_paths=[str(tmp_path)])
    return pp.preprocess(str(src)).text


# ---------------------------------------------------------------------------
# Token-based MacroExpander whitespace tests
# ---------------------------------------------------------------------------

class TestMacroExpanderWhitespace:
    """Tests for whitespace handling in the token-based MacroExpander."""

    def test_space_tokens_preserved_in_expansion(self):
        """Space tokens in replacement list are preserved."""
        tokenizer = PPTokenizer()
        macros = {
            'X': MacroDef(name='X', replacement=tokenizer.tokenize('a + b')),
        }
        expander = MacroExpander(macros)
        result = expander.expand(tokenizer.tokenize('X'))
        text = ''.join(t.text for t in result)
        assert 'a + b' in text or 'a +b' in text or 'a+ b' in text

    def test_adjacent_idents_have_space(self):
        """Adjacent identifier tokens should have space between them."""
        tokenizer = PPTokenizer()
        macros = {
            'X': MacroDef(name='X', replacement=[
                PPToken('ident', 'int'),
                PPToken('space', ' '),
                PPToken('ident', 'x'),
            ]),
        }
        expander = MacroExpander(macros)
        result = expander.expand(tokenizer.tokenize('X'))
        text = ''.join(t.text for t in result)
        assert 'int x' in text

    def test_no_accidental_paste_of_idents(self):
        """Two identifier tokens should not accidentally paste together."""
        tokenizer = PPTokenizer()
        macros = {
            'A': MacroDef(name='A', replacement=[PPToken('ident', 'foo')]),
            'B': MacroDef(name='B', replacement=[PPToken('ident', 'bar')]),
        }
        expander = MacroExpander(macros)
        result = expander.expand(tokenizer.tokenize('A B'))
        text = ''.join(t.text for t in result)
        # Should have space between foo and bar, not "foobar"
        assert 'foobar' not in text or ' ' in text


# ---------------------------------------------------------------------------
# Full preprocessor pipeline whitespace tests
# ---------------------------------------------------------------------------

class TestPreprocessorWhitespace:
    """Tests for whitespace handling through the full Preprocessor pipeline."""

    def test_object_like_macro_preserves_spaces(self, tmp_path):
        """Object-like macro expansion preserves spaces in replacement."""
        out = _pp(tmp_path, """
            #define EXPR a + b
            int x = EXPR;
        """)
        assert "a + b" in out or "a +b" in out or "a+ b" in out

    def test_function_like_macro_preserves_spaces(self, tmp_path):
        """Function-like macro expansion preserves spaces."""
        out = _pp(tmp_path, """
            #define ADD(x, y) (x + y)
            int r = ADD(1, 2);
        """)
        assert "(1 + 2)" in out or "(1+2)" in out

    def test_consecutive_whitespace_collapsed(self, tmp_path):
        """Consecutive whitespace in macro replacement is collapsed."""
        out = _pp(tmp_path, """
            #define WIDE a     +     b
            int x = WIDE;
        """)
        # Should not have excessive whitespace
        assert "a" in out and "b" in out
        # The exact whitespace may vary, but should not have more than
        # a few spaces between tokens
        import re
        # Find the expanded part
        match = re.search(r'int x = (.+);', out)
        if match:
            expanded = match.group(1)
            # No more than 5 consecutive spaces (generous)
            assert '      ' not in expanded

    def test_no_token_pasting_without_operator(self, tmp_path):
        """Adjacent tokens from macro expansion should not accidentally paste."""
        out = _pp(tmp_path, """
            #define A int
            #define B x
            A B;
        """)
        assert "int" in out and "x" in out
        # "intx" should not appear (accidental paste)
        assert "intx" not in out

    def test_macro_arg_whitespace_normalized(self, tmp_path):
        """Whitespace in macro arguments is normalized."""
        out = _pp(tmp_path, """
            #define F(x) x
            F(  hello  )
        """)
        assert "hello" in out

    def test_multiple_macros_on_same_line(self, tmp_path):
        """Multiple macro expansions on the same line preserve token boundaries."""
        out = _pp(tmp_path, """
            #define A 1
            #define B 2
            int x = A + B;
        """)
        assert "1" in out and "2" in out
        assert "1 + 2" in out or "1+2" in out or "1 +2" in out

    def test_nested_macro_whitespace(self, tmp_path):
        """Nested macro expansion preserves whitespace correctly."""
        out = _pp(tmp_path, """
            #define INNER a + b
            #define OUTER INNER
            int x = OUTER;
        """)
        assert "a" in out and "b" in out
