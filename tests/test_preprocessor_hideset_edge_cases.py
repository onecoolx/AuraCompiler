"""Edge case tests for hide-set algorithm improvements (Task 7.2).

Tests indirect recursive macros (A -> B -> A), independent hide-set contexts,
and correct hide-set propagation/merging during macro expansion.

Validates: Requirements 9.1, 9.2
"""
import tempfile
from pathlib import Path

import pytest

from pycc.preprocessor import MacroExpander, MacroDef, PPToken, Preprocessor


# ---------------------------------------------------------------------------
# Helper: preprocess via full Preprocessor pipeline
# ---------------------------------------------------------------------------

def _pp(code: str) -> str:
    """Preprocess code through the full Preprocessor pipeline."""
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "t.c"
        p.write_text(code)
        pp = Preprocessor(include_paths=[])
        res = pp.preprocess(str(p), initial_macros={})
        assert res.success, "preprocess failed: " + "\n".join(res.errors)
        return res.text


# ---------------------------------------------------------------------------
# Token-based MacroExpander tests (hide-set correctness)
# ---------------------------------------------------------------------------

class TestMacroExpanderHideSet:
    """Tests for the token-based MacroExpander hide-set algorithm."""

    def test_indirect_recursion_A_B_A_terminates(self):
        """A -> B, B -> A: must terminate with A in hide-set."""
        expander = MacroExpander()
        expander.macros['A'] = MacroDef(name='A', replacement=[PPToken('ident', 'B')])
        expander.macros['B'] = MacroDef(name='B', replacement=[PPToken('ident', 'A')])

        result = expander.expand([PPToken('ident', 'A')])
        texts = [t.text for t in result if t.kind != 'space']
        assert texts == ['A']
        assert 'A' in result[0].hide_set
        assert 'B' in result[0].hide_set

    def test_three_way_indirect_recursion_terminates(self):
        """A -> B -> C -> A: must terminate."""
        expander = MacroExpander()
        expander.macros['A'] = MacroDef(name='A', replacement=[PPToken('ident', 'B')])
        expander.macros['B'] = MacroDef(name='B', replacement=[PPToken('ident', 'C')])
        expander.macros['C'] = MacroDef(name='C', replacement=[PPToken('ident', 'A')])

        result = expander.expand([PPToken('ident', 'A')])
        texts = [t.text for t in result if t.kind != 'space']
        assert texts == ['A']
        assert 'A' in result[0].hide_set
        assert 'B' in result[0].hide_set
        assert 'C' in result[0].hide_set

    def test_function_like_indirect_recursion_terminates(self):
        """F(x) -> G(x), G(x) -> F(x): must terminate."""
        expander = MacroExpander()
        expander.macros['F'] = MacroDef(
            name='F', is_function_like=True, params=['x'],
            replacement=[
                PPToken('ident', 'G'), PPToken('punct', '('),
                PPToken('ident', 'x'), PPToken('punct', ')')
            ]
        )
        expander.macros['G'] = MacroDef(
            name='G', is_function_like=True, params=['x'],
            replacement=[
                PPToken('ident', 'F'), PPToken('punct', '('),
                PPToken('ident', 'x'), PPToken('punct', ')')
            ]
        )

        tokens = [
            PPToken('ident', 'F'), PPToken('punct', '('),
            PPToken('number', '1'), PPToken('punct', ')')
        ]
        result = expander.expand(tokens)
        texts = [t.text for t in result if t.kind != 'space']
        # F(1) -> G(1) -> F(1), F is in hide-set so stops
        assert 'F' in texts

    def test_independent_expansion_contexts(self):
        """X -> X + X: each X in result has X in its hide-set."""
        expander = MacroExpander()
        expander.macros['X'] = MacroDef(
            name='X',
            replacement=[
                PPToken('ident', 'X'), PPToken('space', ' '),
                PPToken('punct', '+'), PPToken('space', ' '),
                PPToken('ident', 'X'),
            ]
        )

        result = expander.expand([PPToken('ident', 'X')])
        texts = [t.text for t in result if t.kind != 'space']
        assert texts == ['X', '+', 'X']
        for t in result:
            if t.kind == 'ident' and t.text == 'X':
                assert 'X' in t.hide_set

    def test_mixed_object_function_indirect_recursion(self):
        """A -> F(1), F(x) -> A: must terminate."""
        expander = MacroExpander()
        expander.macros['A'] = MacroDef(
            name='A',
            replacement=[
                PPToken('ident', 'F'), PPToken('punct', '('),
                PPToken('number', '1'), PPToken('punct', ')')
            ]
        )
        expander.macros['F'] = MacroDef(
            name='F', is_function_like=True, params=['x'],
            replacement=[PPToken('ident', 'A')]
        )

        result = expander.expand([PPToken('ident', 'A')])
        texts = [t.text for t in result if t.kind != 'space']
        assert texts == ['A']
        assert 'A' in result[0].hide_set

    def test_hide_set_union_propagation(self):
        """Hide-sets are propagated via union during expansion."""
        expander = MacroExpander()
        # A -> B, B -> 42
        expander.macros['A'] = MacroDef(name='A', replacement=[PPToken('ident', 'B')])
        expander.macros['B'] = MacroDef(name='B', replacement=[PPToken('number', '42')])

        result = expander.expand([PPToken('ident', 'A')])
        texts = [t.text for t in result if t.kind != 'space']
        assert texts == ['42']
        # The result token should have both A and B in its hide-set
        num_tok = [t for t in result if t.kind == 'number'][0]
        assert 'A' in num_tok.hide_set
        assert 'B' in num_tok.hide_set

    def test_paste_hide_set_intersection(self):
        """## token paste uses intersection of hide-sets."""
        expander = MacroExpander()
        lhs = PPToken('ident', 'foo', hide_set=frozenset({'A', 'B'}))
        rhs = PPToken('ident', 'bar', hide_set=frozenset({'B', 'C'}))
        tokens = [lhs, PPToken('punct', '##'), rhs]
        result = expander._process_paste(tokens)
        assert len(result) == 1
        assert result[0].text == 'foobar'
        assert result[0].hide_set == frozenset({'B'})


# ---------------------------------------------------------------------------
# Full Preprocessor pipeline tests (text-based expansion)
# ---------------------------------------------------------------------------

class TestPreprocessorHideSetPipeline:
    """Tests for hide-set behavior through the full Preprocessor pipeline."""

    def test_three_way_indirect_recursion_terminates(self):
        """A -> B -> C -> A: must terminate through full pipeline."""
        out = _pp("#define A B\n#define B C\n#define C A\nint x = A;\n")
        assert "int x =" in out
        assert len(out) < 200

    def test_mutual_recursion_with_extra_tokens_terminates(self):
        """A -> B + 1, B -> A + 2: must terminate, not grow unboundedly."""
        out = _pp("#define A B + 1\n#define B A + 2\nint x = A;\n")
        assert "int x =" in out
        # Must not grow unboundedly - should be short
        assert len(out) < 100

    def test_function_like_indirect_recursion_terminates(self):
        """F(x) -> G(x), G(x) -> F(x): must terminate."""
        out = _pp("#define F(x) G(x)\n#define G(x) F(x)\nint y = F(1);\n")
        assert "int y =" in out
        assert len(out) < 200

    def test_mixed_object_function_indirect_terminates(self):
        """A -> F(1), F(x) -> A: must terminate."""
        out = _pp("#define A F(1)\n#define F(x) A\nint z = A;\n")
        assert "int z =" in out
        assert len(out) < 200

    def test_chain_expansion_works(self):
        """A -> B -> C -> 42: should fully expand to 42."""
        out = _pp("#define A B\n#define B C\n#define C 42\nint x = A;\n")
        assert "int x = 42" in out

    def test_independent_contexts_both_expand(self):
        """Same macro used in different places should expand independently."""
        out = _pp("#define X 1\n#define A X\n#define B X\nint a = A; int b = B;\n")
        assert "int a = 1" in out
        assert "int b = 1" in out

    def test_self_ref_object_like_stable(self):
        """#define A A produces A (not infinite expansion)."""
        out = _pp("#define A A\nA\n")
        assert out.strip() == "A"

    def test_self_ref_function_like_stable(self):
        """#define F(x) F(x) produces F(1) (not infinite expansion)."""
        out = _pp("#define F(x) F(x)\nF(1)\n")
        assert out.strip() == "F(1)"

    def test_self_ref_with_extra_tokens(self):
        """#define A A + 1 produces A + 1 (not A + 1 + 1 + ...)."""
        out = _pp("#define A A + 1\nint x = A;\n")
        assert "int x = A + 1" in out

    def test_non_recursive_nested_calls_still_work(self):
        """ADD(ADD(1,2), ADD(3,4)) should expand correctly (not blocked)."""
        out = _pp("#define ADD(a,b) ((a)+(b))\nint x = ADD(ADD(1,2), ADD(3,4));\n")
        assert "((1)+(2))" in out or "(1)+(2)" in out
        assert "((3)+(4))" in out or "(3)+(4)" in out
