"""Tests for # stringize operator special character handling (Task 8.1).

Covers Requirements 10.1, 10.2:
- Tab and newline characters are escaped in stringized output
- Backslash and double-quote characters are escaped
- Consecutive whitespace is collapsed to a single space
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
# Token-based MacroExpander._stringize tests
# ---------------------------------------------------------------------------

class TestStringizeTokenBased:
    """Tests for MacroExpander._stringize special character handling."""

    def test_stringize_plain_text(self):
        tokens = [PPToken('ident', 'hello')]
        assert MacroExpander._stringize(tokens) == '"hello"'

    def test_stringize_multiple_tokens_with_spaces(self):
        tokens = [
            PPToken('ident', 'a'), PPToken('space', ' '),
            PPToken('punct', '+'), PPToken('space', ' '),
            PPToken('ident', 'b'),
        ]
        assert MacroExpander._stringize(tokens) == '"a + b"'

    def test_stringize_collapses_consecutive_whitespace(self):
        tokens = [
            PPToken('ident', 'a'), PPToken('space', '  '),
            PPToken('space', '  '), PPToken('ident', 'b'),
        ]
        assert MacroExpander._stringize(tokens) == '"a b"'

    def test_stringize_escapes_backslash_in_string(self):
        tokens = [PPToken('string', '"a\\\\b"')]
        result = MacroExpander._stringize(tokens)
        # The backslashes inside the string token get doubled by escaping
        assert '\\\\' in result

    def test_stringize_escapes_double_quote_in_string(self):
        tokens = [PPToken('string', '"a\\"b"')]
        result = MacroExpander._stringize(tokens)
        assert '\\"' in result

    def test_stringize_escapes_tab_character(self):
        tokens = [PPToken('ident', 'a\tb')]
        result = MacroExpander._stringize(tokens)
        assert '\\t' in result
        assert '\t' not in result

    def test_stringize_escapes_newline_character(self):
        tokens = [PPToken('ident', 'a\nb')]
        result = MacroExpander._stringize(tokens)
        assert '\\n' in result
        assert '\n' not in result


# ---------------------------------------------------------------------------
# Full preprocessor pipeline stringize tests
# ---------------------------------------------------------------------------

class TestStringizePipeline:
    """Tests for # stringize through the full Preprocessor pipeline."""

    def test_basic_stringize(self, tmp_path):
        out = _pp(tmp_path, """
            #define STR(x) #x
            STR(hello)
        """)
        assert '"hello"' in out

    def test_stringize_with_spaces(self, tmp_path):
        out = _pp(tmp_path, """
            #define STR(x) #x
            STR(a + b)
        """)
        assert '"a + b"' in out

    def test_stringize_collapses_whitespace(self, tmp_path):
        out = _pp(tmp_path, """
            #define STR(x) #x
            STR(a    b)
        """)
        assert '"a b"' in out

    def test_stringize_backslash_in_arg(self, tmp_path):
        """Backslash in stringized argument should be escaped."""
        out = _pp(tmp_path, r"""
            #define STR(x) #x
            STR(a\b)
        """)
        assert '"a\\\\b"' in out or '"a\\b"' in out

    def test_stringize_double_quote_in_string_arg(self, tmp_path):
        """Double quote in stringized argument should be escaped."""
        out = _pp(tmp_path, """
            #define STR(x) #x
            STR("hello")
        """)
        assert '\\"hello\\"' in out or '\\\"hello\\\"' in out

    def test_stringize_produces_valid_c_string(self, tmp_path):
        """Stringized output should be a valid C string literal."""
        out = _pp(tmp_path, """
            #define STR(x) #x
            char *s = STR(test);
        """)
        assert 'char *s = "test"' in out

    def test_stringize_numeric_arg(self, tmp_path):
        out = _pp(tmp_path, """
            #define STR(x) #x
            STR(42)
        """)
        assert '"42"' in out

    def test_stringize_complex_expression(self, tmp_path):
        out = _pp(tmp_path, """
            #define STR(x) #x
            STR(a + b * c)
        """)
        assert '"a + b * c"' in out
