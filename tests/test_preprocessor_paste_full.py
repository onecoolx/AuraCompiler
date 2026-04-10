"""Tests for ## token paste validation and rescan (Task 9.1).

Covers Requirements 11.1, 11.2:
- Valid paste results are rescanned for further macro expansion
- Invalid paste results produce diagnostic information
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
# Token-based MacroExpander._process_paste tests
# ---------------------------------------------------------------------------

class TestProcessPaste:
    """Tests for MacroExpander._process_paste validation."""

    def test_paste_two_idents(self):
        """Pasting two identifiers produces a valid identifier."""
        expander = MacroExpander()
        tokens = [
            PPToken('ident', 'foo'),
            PPToken('punct', '##'),
            PPToken('ident', 'bar'),
        ]
        result = expander._process_paste(tokens)
        assert len(result) == 1
        assert result[0].text == 'foobar'
        assert result[0].kind == 'ident'

    def test_paste_ident_and_number(self):
        """Pasting identifier and number produces a valid token."""
        expander = MacroExpander()
        tokens = [
            PPToken('ident', 'x'),
            PPToken('punct', '##'),
            PPToken('number', '42'),
        ]
        result = expander._process_paste(tokens)
        assert len(result) == 1
        assert result[0].text == 'x42'
        assert result[0].kind == 'ident'

    def test_paste_two_numbers(self):
        """Pasting two numbers produces a valid number token."""
        expander = MacroExpander()
        tokens = [
            PPToken('number', '1'),
            PPToken('punct', '##'),
            PPToken('number', '2'),
        ]
        result = expander._process_paste(tokens)
        assert len(result) == 1
        assert result[0].text == '12'
        assert result[0].kind == 'number'

    def test_paste_producing_operator(self):
        """Pasting < and = produces <=."""
        expander = MacroExpander()
        tokens = [
            PPToken('punct', '<'),
            PPToken('punct', '##'),
            PPToken('punct', '='),
        ]
        result = expander._process_paste(tokens)
        assert len(result) == 1
        assert result[0].text == '<='
        assert result[0].kind == 'punct'

    def test_paste_invalid_produces_diagnostic(self, capsys):
        """Pasting tokens that don't form a valid token produces a warning."""
        expander = MacroExpander()
        tokens = [
            PPToken('punct', ')'),
            PPToken('punct', '##'),
            PPToken('punct', '('),
        ]
        result = expander._process_paste(tokens)
        assert len(result) == 1
        assert result[0].text == ')('
        assert result[0].kind == 'other'
        captured = capsys.readouterr()
        assert 'does not give a valid preprocessing token' in captured.err

    def test_paste_hide_set_intersection(self):
        """## paste uses intersection of hide-sets."""
        expander = MacroExpander()
        tokens = [
            PPToken('ident', 'a', hide_set=frozenset({'X', 'Y'})),
            PPToken('punct', '##'),
            PPToken('ident', 'b', hide_set=frozenset({'Y', 'Z'})),
        ]
        result = expander._process_paste(tokens)
        assert len(result) == 1
        assert result[0].hide_set == frozenset({'Y'})


# ---------------------------------------------------------------------------
# Full pipeline paste + rescan tests
# ---------------------------------------------------------------------------

class TestPastePipeline:
    """Tests for ## paste through the full Preprocessor pipeline."""

    def test_paste_producing_macro_name_rescanned(self, tmp_path):
        """Req 11.1: paste result that is a macro name gets rescanned."""
        out = _pp(tmp_path, """
            #define CAT(a,b) a##b
            #define XY 42
            int x = CAT(X,Y);
        """)
        assert "int x = 42" in out

    def test_paste_producing_function_macro_name(self, tmp_path):
        """Req 11.1: paste result that is a function macro name gets rescanned."""
        out = _pp(tmp_path, """
            #define CAT(a,b) a##b
            #define FN(x) (x+1)
            int x = CAT(F,N)(5);
        """)
        assert "(5+1)" in out

    def test_paste_basic_concat(self, tmp_path):
        """Basic token paste concatenation."""
        out = _pp(tmp_path, """
            #define PASTE(a,b) a##b
            int PASTE(var,1) = 10;
        """)
        assert "int var1 = 10" in out

    def test_paste_number_concat(self, tmp_path):
        """Pasting numbers together."""
        out = _pp(tmp_path, """
            #define PASTE(a,b) a##b
            int x = PASTE(1,23);
        """)
        assert "int x = 123" in out
