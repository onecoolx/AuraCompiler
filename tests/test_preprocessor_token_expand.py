"""Tests for multi-round rescan and token-based macro expansion (C89 §6.8.3).

Covers Requirements 8.1, 8.2, 8.3:
- Nested macro calls in expansion results are recursively expanded
- Expansion results are rescanned until no more macros can be expanded
- Self-referential and mutually recursive macros terminate correctly
"""
import textwrap

from pycc.preprocessor import Preprocessor


def _pp_text(tmp_path, source_text: str) -> str:
    src = tmp_path / "main.c"
    src.write_text(textwrap.dedent(source_text).lstrip(), encoding="utf-8")
    pp = Preprocessor(include_paths=[str(tmp_path)])
    return pp.preprocess(str(src)).text


# ---------------------------------------------------------------------------
# Requirement 8.1: Nested macro calls in expansion results are expanded
# ---------------------------------------------------------------------------

def test_chained_object_like_macros_fully_expand(tmp_path):
    """A -> B -> C -> 42: chained object-like macros must fully resolve."""
    out = _pp_text(tmp_path, """\
        #define A B
        #define B C
        #define C 42
        int x = A;
    """)
    assert "int x = 42;" in out


def test_nested_function_like_macros(tmp_path):
    """G(5) -> F(5) -> (5+1): nested function-like calls must expand."""
    out = _pp_text(tmp_path, """\
        #define F(x) (x+1)
        #define G(x) F(x)
        G(5)
    """)
    assert "(5+1)" in out


def test_triple_nested_function_like_macros(tmp_path):
    """DOUBLE(INC(3)) must fully expand all nested calls."""
    out = _pp_text(tmp_path, """\
        #define ADD(a,b) ((a)+(b))
        #define INC(x) ADD(x,1)
        #define DOUBLE(x) ADD(x,x)
        DOUBLE(INC(3))
    """)
    # INC(3) -> ADD(3,1) -> ((3)+(1))
    # DOUBLE(((3)+(1))) -> ADD(((3)+(1)),((3)+(1))) -> ((((3)+(1)))+(((3)+(1))))
    assert "((((3)+(1)))+(((3)+(1))))" in out


def test_same_macro_nested_in_args(tmp_path):
    """ADD(ADD(1,2), ADD(3,4)) must expand inner calls."""
    out = _pp_text(tmp_path, """\
        #define ADD(a,b) ((a)+(b))
        ADD(ADD(1,2), ADD(3,4))
    """)
    assert "((((1)+(2)))+(((3)+(4))))" in out


def test_macro_arg_contains_object_like_macro(tmp_path):
    """F(X) where X is an object-like macro must expand X in the argument."""
    out = _pp_text(tmp_path, """\
        #define X 3
        #define F(a) (a+1)
        F(X)
    """)
    assert "(3+1)" in out


def test_multiple_macros_in_args(tmp_path):
    """ADD(A, B) where A and B are object-like macros."""
    out = _pp_text(tmp_path, """\
        #define A 1
        #define B 2
        #define ADD(x,y) (x+y)
        ADD(A, B)
    """)
    assert "(1+2)" in out


# ---------------------------------------------------------------------------
# Requirement 8.2: Rescan until no more macros can be expanded
# ---------------------------------------------------------------------------

def test_object_like_expanding_to_function_like_call(tmp_path):
    """Object-like macro expanding to a function-like call must be rescanned."""
    out = _pp_text(tmp_path, """\
        #define F(x) (x*10)
        #define CALL F(5)
        int x = CALL;
    """)
    assert "int x = (5*10);" in out


def test_deep_chain_object_to_function_like(tmp_path):
    """A -> B(1) -> C(1) -> 1+1: object-like expanding to fn-like chain."""
    out = _pp_text(tmp_path, """\
        #define A B(1)
        #define B(x) C(x)
        #define C(x) x+1
        A
    """)
    assert "1+1" in out


def test_macro_producing_another_macro_call(tmp_path):
    """APPLY(DOUBLE, 3) -> DOUBLE(3) -> (3 * 2)."""
    out = _pp_text(tmp_path, """\
        #define DOUBLE(x) (x * 2)
        #define APPLY(f, x) f(x)
        APPLY(DOUBLE, 3)
    """)
    assert "(3 * 2)" in out


def test_paste_producing_macro_name_rescanned(tmp_path):
    """Token paste producing a macro name must be rescanned."""
    out = _pp_text(tmp_path, """\
        #define CAT(a,b) a##b
        #define XY 42
        CAT(X,Y)
    """)
    assert "42" in out


# ---------------------------------------------------------------------------
# Requirement 8.3: Self-referential macros terminate correctly
# ---------------------------------------------------------------------------

def test_self_referential_object_like_terminates(tmp_path):
    """#define A A + 1 must expand once and stop."""
    out = _pp_text(tmp_path, """\
        #define A A + 1
        int x = A;
    """)
    assert "int x = A + 1;" in out


def test_self_referential_function_like_terminates(tmp_path):
    """#define F(x) F(x) + 1 must expand once and stop."""
    out = _pp_text(tmp_path, """\
        #define F(x) F(x) + 1
        int a = F(0);
    """)
    assert "int a = F(0) + 1;" in out


def test_mutual_recursion_object_like_terminates(tmp_path):
    """A -> B -> A: mutual recursion must terminate."""
    out = _pp_text(tmp_path, """\
        #define A B
        #define B A
        int x = A;
    """)
    # Must terminate; the exact stabilized result is acceptable
    assert "int x = A;" in out or "int x = B;" in out


def test_mutual_recursion_function_like_terminates(tmp_path):
    """F(x) -> G(x) -> F(x): mutual recursion must terminate."""
    out = _pp_text(tmp_path, """\
        #define F(x) G(x)
        #define G(x) F(x)
        F(1)
    """)
    assert "F(1)" in out or "G(1)" in out


def test_self_referential_wrapped_terminates(tmp_path):
    """WRAP(A) where A is self-referential must expand once."""
    out = _pp_text(tmp_path, """\
        #define A A + 1
        #define WRAP(x) x
        WRAP(A)
    """)
    assert out.strip() == "A + 1"


# ---------------------------------------------------------------------------
# Additional complex scenarios
# ---------------------------------------------------------------------------

def test_four_level_chain(tmp_path):
    """Four-level chained object-like macros."""
    out = _pp_text(tmp_path, """\
        #define W X
        #define X Y
        #define Y Z
        #define Z 99
        int v = W;
    """)
    assert "int v = 99;" in out


def test_fn_macro_result_contains_obj_macro(tmp_path):
    """Function-like macro result containing object-like macro names."""
    out = _pp_text(tmp_path, """\
        #define VAL 42
        #define GET() VAL
        int x = GET();
    """)
    assert "int x = 42;" in out


def test_multiple_fn_calls_on_same_line(tmp_path):
    """Multiple function-like macro calls on the same line."""
    out = _pp_text(tmp_path, """\
        #define F(x) (x+1)
        int a = F(1) + F(2);
    """)
    assert "int a = (1+1) + (2+1);" in out
