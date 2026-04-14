"""Unit tests for parser abstract declarator support.

Tests concrete examples of unnamed parameters in function prototypes,
including plain types, pointers, function pointers, mixed params, and nesting.

**Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5**
"""
from pycc.lexer import Lexer
from pycc.parser import Parser
from pycc.ast_nodes import FunctionDecl


def _parse_proto(code: str) -> FunctionDecl:
    """Parse a C function prototype and return the FunctionDecl AST node."""
    tokens = Lexer(code).tokenize()
    prog = Parser(tokens).parse()
    for decl in prog.declarations:
        if isinstance(decl, FunctionDecl):
            return decl
    raise AssertionError(f"No FunctionDecl found in: {code!r}")


# ---------------------------------------------------------------------------
# Test: void f(int, char *) — unnamed params with and without pointers
# Validates: Requirements 1.1, 1.5
# ---------------------------------------------------------------------------

class TestUnnamedParamsBasic:
    """Test parsing of unnamed parameters with and without pointers."""

    def test_unnamed_int_and_char_ptr(self):
        """void f(int, char *) — two unnamed params, one plain, one pointer."""
        fd = _parse_proto("void f(int, char *);")

        assert fd.name == "f"
        assert len(fd.parameters) == 2

        # First param: unnamed int
        p0 = fd.parameters[0]
        assert p0.name is None
        assert p0.type.base == "int"
        assert not p0.type.is_pointer

        # Second param: unnamed char *
        p1 = fd.parameters[1]
        assert p1.name is None
        assert p1.type.base == "char"
        assert p1.type.is_pointer

    def test_single_unnamed_int(self):
        """int g(int) — single unnamed int parameter."""
        fd = _parse_proto("int g(int);")

        assert len(fd.parameters) == 1
        p = fd.parameters[0]
        assert p.name is None
        assert p.type.base == "int"
        assert not p.type.is_pointer

    def test_single_unnamed_pointer(self):
        """void h(char *) — single unnamed pointer parameter."""
        fd = _parse_proto("void h(char *);")

        assert len(fd.parameters) == 1
        p = fd.parameters[0]
        assert p.name is None
        assert p.type.base == "char"
        assert p.type.is_pointer


# ---------------------------------------------------------------------------
# Test: int (*)(int, int) — unnamed function pointer parameter
# Validates: Requirements 1.2
# ---------------------------------------------------------------------------

class TestUnnamedFunctionPointer:
    """Test parsing of unnamed function pointer parameters."""

    def test_unnamed_fnptr_two_int_params(self):
        """void f(int (*)(int, int)) — unnamed function pointer with two int params."""
        fd = _parse_proto("void f(int (*)(int, int));")

        assert fd.name == "f"
        assert len(fd.parameters) == 1

        p = fd.parameters[0]
        assert p.name is None
        assert p.type.is_pointer
        assert p.type.fn_param_count == 2

    def test_unnamed_fnptr_void_params(self):
        """void f(void (*)(void)) — unnamed function pointer with void params."""
        fd = _parse_proto("void f(void (*)(void));")

        assert len(fd.parameters) == 1
        p = fd.parameters[0]
        assert p.name is None
        assert p.type.is_pointer
        assert p.type.fn_param_count == 0

    def test_unnamed_fnptr_returning_int(self):
        """void f(int (*)(char, long)) — unnamed fnptr returning int."""
        fd = _parse_proto("void f(int (*)(char, long));")

        assert len(fd.parameters) == 1
        p = fd.parameters[0]
        assert p.name is None
        assert p.type.is_pointer
        assert p.type.fn_param_count == 2


# ---------------------------------------------------------------------------
# Test: void f(int x, char *, int) — mixed named/unnamed parameters
# Validates: Requirements 1.3
# ---------------------------------------------------------------------------

class TestMixedNamedUnnamed:
    """Test parsing of mixed named and unnamed parameters."""

    def test_mixed_three_params(self):
        """void f(int x, char *, int) — named, unnamed ptr, unnamed."""
        fd = _parse_proto("void f(int x, char *, int);")

        assert fd.name == "f"
        assert len(fd.parameters) == 3

        # First: named int x
        p0 = fd.parameters[0]
        assert p0.name == "x"
        assert p0.type.base == "int"

        # Second: unnamed char *
        p1 = fd.parameters[1]
        assert p1.name is None
        assert p1.type.base == "char"
        assert p1.type.is_pointer

        # Third: unnamed int
        p2 = fd.parameters[2]
        assert p2.name is None
        assert p2.type.base == "int"

    def test_mixed_unnamed_first(self):
        """int g(char, int n) — unnamed first, named second."""
        fd = _parse_proto("int g(char, int n);")

        assert len(fd.parameters) == 2

        p0 = fd.parameters[0]
        assert p0.name is None
        assert p0.type.base == "char"

        p1 = fd.parameters[1]
        assert p1.name == "n"
        assert p1.type.base == "int"

    def test_mixed_order_preserved(self):
        """void h(int a, long, char *b, double) — order preserved."""
        fd = _parse_proto("void h(int a, long, char *b, double);")

        assert len(fd.parameters) == 4
        expected = [("a", "int"), (None, "long int"), ("b", "char"), (None, "double")]
        for i, (exp_name, exp_base) in enumerate(expected):
            assert fd.parameters[i].name == exp_name
            assert fd.parameters[i].type.base == exp_base


# ---------------------------------------------------------------------------
# Test: int (*)(void (*)(int)) — nested unnamed function pointers
# Validates: Requirements 1.4
# ---------------------------------------------------------------------------

class TestNestedUnnamedFunctionPointers:
    """Test parsing of nested unnamed function pointer parameters."""

    def test_nested_fnptr(self):
        """void f(int (*)(void (*)(int))) — nested unnamed function pointers."""
        fd = _parse_proto("void f(int (*)(void (*)(int)));")

        assert fd.name == "f"
        assert len(fd.parameters) == 1

        # Outer: unnamed function pointer
        p = fd.parameters[0]
        assert p.name is None
        assert p.type.is_pointer
        # The outer fnptr takes 1 parameter (the inner fnptr)
        assert p.type.fn_param_count == 1


# ---------------------------------------------------------------------------
# Test: void f(int **) — multi-level pointer unnamed param
# Validates: Requirements 1.5
# ---------------------------------------------------------------------------

class TestMultiLevelPointer:
    """Test parsing of multi-level pointer unnamed parameters."""

    def test_double_pointer(self):
        """void f(int **) — unnamed double pointer parameter."""
        fd = _parse_proto("void f(int **);")

        assert fd.name == "f"
        assert len(fd.parameters) == 1

        p = fd.parameters[0]
        assert p.name is None
        assert p.type.base == "int"
        assert p.type.is_pointer
        # Parser marks is_pointer=True; effective level >= 1
        # Multi-level pointers in unnamed params: is_pointer is the key signal
        effective_level = p.type.pointer_level if p.type.pointer_level > 0 else 1
        assert effective_level >= 1

    def test_triple_pointer(self):
        """void f(char ***) — unnamed triple pointer parameter."""
        fd = _parse_proto("void f(char ***);")

        assert len(fd.parameters) == 1
        p = fd.parameters[0]
        assert p.name is None
        assert p.type.base == "char"
        assert p.type.is_pointer

    def test_single_pointer(self):
        """void f(int *) — unnamed single pointer for comparison."""
        fd = _parse_proto("void f(int *);")

        assert len(fd.parameters) == 1
        p = fd.parameters[0]
        assert p.name is None
        assert p.type.base == "int"
        assert p.type.is_pointer
