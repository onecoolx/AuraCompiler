"""Tests for the token-based MacroExpander rescan logic.

Verifies that the PPToken-based MacroExpander correctly implements
multi-round rescan per C89 §6.8.3.
"""
from pycc.preprocessor import MacroExpander, MacroDef, PPToken, PPTokenizer


def _expand_text(macro_defs: dict, text: str) -> str:
    """Helper: define macros and expand text, returning the result as a string."""
    tokenizer = PPTokenizer()
    macros = {}
    for name, defn in macro_defs.items():
        if isinstance(defn, str):
            # Object-like macro
            macros[name] = MacroDef(
                name=name,
                is_function_like=False,
                replacement=tokenizer.tokenize(defn),
            )
        else:
            # Function-like macro: (params, body)
            params, body = defn
            macros[name] = MacroDef(
                name=name,
                is_function_like=True,
                params=params,
                replacement=tokenizer.tokenize(body),
            )
    expander = MacroExpander(macros)
    tokens = tokenizer.tokenize(text)
    result = expander.expand(tokens)
    return "".join(t.text for t in result)


# ---------------------------------------------------------------------------
# Object-like macro rescan
# ---------------------------------------------------------------------------

def test_expander_chained_object_like():
    """A -> B -> C -> 42"""
    result = _expand_text({"A": "B", "B": "C", "C": "42"}, "A")
    assert result.strip() == "42"


def test_expander_self_referential_object_like():
    """#define A A + 1 -> A + 1 (no infinite expansion)"""
    result = _expand_text({"A": "A + 1"}, "A")
    assert result.strip() == "A + 1"


def test_expander_mutual_recursion_object_like():
    """A -> B -> A terminates"""
    result = _expand_text({"A": "B", "B": "A"}, "A")
    assert result.strip() in ("A", "B")


# ---------------------------------------------------------------------------
# Function-like macro rescan
# ---------------------------------------------------------------------------

def test_expander_nested_function_like():
    """G(5) -> F(5) -> (5+1)"""
    result = _expand_text(
        {"F": (["x"], "(x+1)"), "G": (["x"], "F(x)")},
        "G(5)",
    )
    assert "(5+1)" in result


def test_expander_same_macro_nested_in_args():
    """ADD(ADD(1,2), ADD(3,4)) fully expands."""
    result = _expand_text(
        {"ADD": (["a", "b"], "((a)+(b))")},
        "ADD(ADD(1,2), ADD(3,4))",
    )
    # Normalize whitespace for comparison
    normalized = "".join(result.split())
    assert "((((1)+(2)))+(((3)+(4))))" in normalized


def test_expander_self_referential_function_like():
    """#define F(x) F(x) + 1 -> F(0) + 1"""
    result = _expand_text(
        {"F": (["x"], "F(x) + 1")},
        "F(0)",
    )
    assert "F(0) + 1" in result
    # Must not grow beyond one expansion
    assert result.count("+ 1") == 1


def test_expander_mutual_recursion_function_like():
    """F(x) -> G(x) -> F(x) terminates"""
    result = _expand_text(
        {"F": (["x"], "G(x)"), "G": (["x"], "F(x)")},
        "F(1)",
    )
    assert "F(1)" in result or "G(1)" in result


def test_expander_macro_producing_another_call():
    """APPLY(DOUBLE, 3) -> DOUBLE(3) -> (3*2)"""
    result = _expand_text(
        {"DOUBLE": (["x"], "(x*2)"), "APPLY": (["f", "x"], "f(x)")},
        "APPLY(DOUBLE, 3)",
    )
    normalized = "".join(result.split())
    assert "(3*2)" in normalized


def test_expander_triple_nesting():
    """DOUBLE(INC(3)) fully expands."""
    result = _expand_text(
        {
            "ADD": (["a", "b"], "((a)+(b))"),
            "INC": (["x"], "ADD(x,1)"),
            "DOUBLE": (["x"], "ADD(x,x)"),
        },
        "DOUBLE(INC(3))",
    )
    assert "((((3)+(1)))+(((3)+(1))))" in result


# ---------------------------------------------------------------------------
# Token paste + rescan
# ---------------------------------------------------------------------------

def test_expander_paste_producing_macro_name():
    """CAT(X,Y) -> XY -> 42"""
    result = _expand_text(
        {"CAT": (["a", "b"], "a##b"), "XY": "42"},
        "CAT(X,Y)",
    )
    assert "42" in result
