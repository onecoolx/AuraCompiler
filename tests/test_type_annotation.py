"""Unit tests for expression type annotation skeleton methods.

Tests _annotate_type, _resolve_identifier_ctype, and _decay_type methods
added to SemanticAnalyzer as part of the expr-type-annotation feature.
"""

import pytest

from pycc.semantics import SemanticAnalyzer
from pycc.ast_nodes import Type as ASTType
from pycc.types import (
    ArrayType,
    CType,
    FloatType,
    FunctionTypeCType,
    IntegerType,
    PointerType,
    TypeKind,
)


@pytest.fixture
def analyzer():
    """Create a SemanticAnalyzer with minimal state for testing."""
    sa = SemanticAnalyzer()
    sa._decl_types = {}
    sa._global_decl_types = {}
    return sa


class TestAnnotateType:
    """Tests for _annotate_type method."""

    def test_sets_resolved_type(self, analyzer):
        class Expr:
            pass

        expr = Expr()
        ct = IntegerType(kind=TypeKind.INT)
        analyzer._annotate_type(expr, ct)
        assert expr.resolved_type is ct

    def test_returns_ctype(self, analyzer):
        class Expr:
            pass

        expr = Expr()
        ct = FloatType(kind=TypeKind.DOUBLE)
        result = analyzer._annotate_type(expr, ct)
        assert result is ct

    def test_none_ctype(self, analyzer):
        class Expr:
            pass

        expr = Expr()
        result = analyzer._annotate_type(expr, None)
        assert expr.resolved_type is None
        assert result is None


class TestDecayType:
    """Tests for _decay_type method."""

    def test_array_decays_to_pointer(self, analyzer):
        elem = IntegerType(kind=TypeKind.INT)
        arr = ArrayType(kind=TypeKind.ARRAY, element=elem, size=5)
        result = analyzer._decay_type(arr)
        assert isinstance(result, PointerType)
        assert result.kind == TypeKind.POINTER
        assert result.pointee is elem

    def test_function_decays_to_pointer(self, analyzer):
        func = FunctionTypeCType(
            kind=TypeKind.FUNCTION,
            return_type=IntegerType(kind=TypeKind.INT),
            param_types=[IntegerType(kind=TypeKind.INT)],
        )
        result = analyzer._decay_type(func)
        assert isinstance(result, PointerType)
        assert result.kind == TypeKind.POINTER
        assert result.pointee is func

    def test_integer_passthrough(self, analyzer):
        ct = IntegerType(kind=TypeKind.INT)
        assert analyzer._decay_type(ct) is ct

    def test_pointer_passthrough(self, analyzer):
        ct = PointerType(kind=TypeKind.POINTER, pointee=IntegerType(kind=TypeKind.INT))
        assert analyzer._decay_type(ct) is ct

    def test_float_passthrough(self, analyzer):
        ct = FloatType(kind=TypeKind.DOUBLE)
        assert analyzer._decay_type(ct) is ct

    def test_none_returns_none(self, analyzer):
        assert analyzer._decay_type(None) is None

    def test_array_of_pointers_decays(self, analyzer):
        elem = PointerType(kind=TypeKind.POINTER, pointee=IntegerType(kind=TypeKind.CHAR))
        arr = ArrayType(kind=TypeKind.ARRAY, element=elem, size=3)
        result = analyzer._decay_type(arr)
        assert isinstance(result, PointerType)
        assert result.pointee is elem


class TestResolveIdentifierCtype:
    """Tests for _resolve_identifier_ctype method."""

    def test_not_found_returns_none(self, analyzer):
        assert analyzer._resolve_identifier_ctype("unknown") is None

    def test_local_int(self, analyzer):
        analyzer._decl_types = {"x": ASTType(line=0, column=0, base="int")}
        result = analyzer._resolve_identifier_ctype("x")
        assert result is not None
        assert result.kind == TypeKind.INT

    def test_local_pointer(self, analyzer):
        analyzer._decl_types = {
            "p": ASTType(line=0, column=0, base="int", is_pointer=True, pointer_level=1)
        }
        result = analyzer._resolve_identifier_ctype("p")
        assert isinstance(result, PointerType)
        assert result.kind == TypeKind.POINTER
        assert result.pointee.kind == TypeKind.INT

    def test_global_fallback(self, analyzer):
        analyzer._decl_types = {}
        analyzer._global_decl_types = {"g": ASTType(line=0, column=0, base="long")}
        result = analyzer._resolve_identifier_ctype("g")
        assert result is not None
        assert result.kind == TypeKind.LONG

    def test_local_shadows_global(self, analyzer):
        analyzer._decl_types = {"x": ASTType(line=0, column=0, base="char")}
        analyzer._global_decl_types = {"x": ASTType(line=0, column=0, base="long")}
        result = analyzer._resolve_identifier_ctype("x")
        assert result.kind == TypeKind.CHAR

    def test_typedef_resolution(self, analyzer):
        # Set up a typedef: MyInt -> int
        analyzer._typedefs = [{"MyInt": ASTType(line=0, column=0, base="int")}]
        analyzer._decl_types = {"v": ASTType(line=0, column=0, base="MyInt")}
        result = analyzer._resolve_identifier_ctype("v")
        assert result is not None
        assert result.kind == TypeKind.INT

    def test_unsigned_int(self, analyzer):
        analyzer._decl_types = {
            "u": ASTType(line=0, column=0, base="int", is_unsigned=True)
        }
        result = analyzer._resolve_identifier_ctype("u")
        assert result is not None
        assert result.kind == TypeKind.INT
        assert result.is_unsigned is True

    def test_double_pointer(self, analyzer):
        analyzer._decl_types = {
            "pp": ASTType(line=0, column=0, base="char", is_pointer=True, pointer_level=2)
        }
        result = analyzer._resolve_identifier_ctype("pp")
        assert isinstance(result, PointerType)
        assert isinstance(result.pointee, PointerType)
        assert result.pointee.pointee.kind == TypeKind.CHAR
