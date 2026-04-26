"""Unit tests for Parser._build_type_from_specifiers.

Tests the normalization logic that converts collected declaration specifiers
(quals, sign, size, base, tag_type, typedef_name) into a Type node.
This method is not yet wired into _parse_type_specifier_core — it will be
in task 4.  For now we test it directly.
"""
import pytest
from pycc.lexer import Lexer, Token, TokenType
from pycc.parser import Parser, ParserError
from pycc.ast_nodes import Type


def _make_parser():
    """Create a minimal Parser instance for calling _build_type_from_specifiers."""
    lex = Lexer("int x;")
    tokens = lex.tokenize()
    return Parser(tokens)


def _dummy_tok(line=1, col=1):
    """Create a dummy token for source location."""
    return Token(type=TokenType.KEYWORD, value="int", line=line, column=col)


# ── Explicit base type keywords ──────────────────────────────────────

class TestExplicitBase:
    def test_plain_int(self):
        p = _make_parser()
        t = p._build_type_from_specifiers(set(), None, None, "int", None, None, _dummy_tok())
        assert t.base == "int"
        assert not t.is_unsigned
        assert not t.is_const

    def test_plain_char(self):
        p = _make_parser()
        t = p._build_type_from_specifiers(set(), None, None, "char", None, None, _dummy_tok())
        assert t.base == "char"

    def test_plain_void(self):
        p = _make_parser()
        t = p._build_type_from_specifiers(set(), None, None, "void", None, None, _dummy_tok())
        assert t.base == "void"

    def test_plain_float(self):
        p = _make_parser()
        t = p._build_type_from_specifiers(set(), None, None, "float", None, None, _dummy_tok())
        assert t.base == "float"

    def test_plain_double(self):
        p = _make_parser()
        t = p._build_type_from_specifiers(set(), None, None, "double", None, None, _dummy_tok())
        assert t.base == "double"

    def test_builtin_va_list(self):
        p = _make_parser()
        t = p._build_type_from_specifiers(set(), None, None, "__builtin_va_list", None, None, _dummy_tok())
        assert t.base == "__builtin_va_list"


# ── Sign + base combinations ────────────────────────────────────────

class TestSignBase:
    def test_unsigned_int(self):
        p = _make_parser()
        t = p._build_type_from_specifiers(set(), "unsigned", None, "int", None, None, _dummy_tok())
        assert t.base == "unsigned int"
        assert t.is_unsigned

    def test_signed_int(self):
        p = _make_parser()
        t = p._build_type_from_specifiers(set(), "signed", None, "int", None, None, _dummy_tok())
        assert t.base == "int"
        assert t.is_signed

    def test_unsigned_char(self):
        p = _make_parser()
        t = p._build_type_from_specifiers(set(), "unsigned", None, "char", None, None, _dummy_tok())
        assert t.base == "unsigned char"

    def test_signed_char(self):
        p = _make_parser()
        t = p._build_type_from_specifiers(set(), "signed", None, "char", None, None, _dummy_tok())
        assert t.base == "char"


# ── Size + base combinations ────────────────────────────────────────

class TestSizeBase:
    def test_short_int(self):
        p = _make_parser()
        t = p._build_type_from_specifiers(set(), None, "short", "int", None, None, _dummy_tok())
        assert t.base == "short int"

    def test_long_int(self):
        p = _make_parser()
        t = p._build_type_from_specifiers(set(), None, "long", "int", None, None, _dummy_tok())
        assert t.base == "long int"

    def test_long_double(self):
        p = _make_parser()
        t = p._build_type_from_specifiers(set(), None, "long", "double", None, None, _dummy_tok())
        assert t.base == "long double"


# ── Sign + size + base combinations ─────────────────────────────────

class TestSignSizeBase:
    def test_unsigned_short_int(self):
        p = _make_parser()
        t = p._build_type_from_specifiers(set(), "unsigned", "short", "int", None, None, _dummy_tok())
        assert t.base == "unsigned short"

    def test_unsigned_long_int(self):
        p = _make_parser()
        t = p._build_type_from_specifiers(set(), "unsigned", "long", "int", None, None, _dummy_tok())
        assert t.base == "unsigned long"


# ── Bare sign/size (implicit int) ───────────────────────────────────

class TestImplicitInt:
    def test_bare_unsigned(self):
        p = _make_parser()
        t = p._build_type_from_specifiers(set(), "unsigned", None, None, None, None, _dummy_tok())
        assert t.base == "unsigned int"
        assert t.is_unsigned

    def test_bare_signed(self):
        p = _make_parser()
        t = p._build_type_from_specifiers(set(), "signed", None, None, None, None, _dummy_tok())
        assert t.base == "int"
        assert t.is_signed

    def test_bare_short(self):
        p = _make_parser()
        t = p._build_type_from_specifiers(set(), None, "short", None, None, None, _dummy_tok())
        assert t.base == "short int"

    def test_bare_long(self):
        p = _make_parser()
        t = p._build_type_from_specifiers(set(), None, "long", None, None, None, _dummy_tok())
        assert t.base == "long int"

    def test_unsigned_short(self):
        p = _make_parser()
        t = p._build_type_from_specifiers(set(), "unsigned", "short", None, None, None, _dummy_tok())
        assert t.base == "unsigned short"

    def test_unsigned_long(self):
        p = _make_parser()
        t = p._build_type_from_specifiers(set(), "unsigned", "long", None, None, None, _dummy_tok())
        assert t.base == "unsigned long"


# ── Qualifier propagation ────────────────────────────────────────────

class TestQualifiers:
    def test_const_int(self):
        p = _make_parser()
        t = p._build_type_from_specifiers({"const"}, None, None, "int", None, None, _dummy_tok())
        assert t.base == "int"
        assert t.is_const
        assert not t.is_volatile

    def test_volatile_int(self):
        p = _make_parser()
        t = p._build_type_from_specifiers({"volatile"}, None, None, "int", None, None, _dummy_tok())
        assert t.is_volatile
        assert not t.is_const

    def test_const_volatile_int(self):
        p = _make_parser()
        t = p._build_type_from_specifiers({"const", "volatile"}, None, None, "int", None, None, _dummy_tok())
        assert t.is_const
        assert t.is_volatile

    def test_const_unsigned_long(self):
        p = _make_parser()
        t = p._build_type_from_specifiers({"const"}, "unsigned", "long", None, None, None, _dummy_tok())
        assert t.base == "unsigned long"
        assert t.is_const
        assert t.is_unsigned


# ── tag_type passthrough (struct/union/enum) ─────────────────────────

class TestTagType:
    def test_struct_passthrough(self):
        p = _make_parser()
        tag = Type(base="struct Foo", line=1, column=1)
        t = p._build_type_from_specifiers(set(), None, None, None, tag, None, _dummy_tok())
        assert t.base == "struct Foo"
        assert t is tag  # same object, mutated in place

    def test_const_struct(self):
        p = _make_parser()
        tag = Type(base="struct Foo", line=1, column=1)
        t = p._build_type_from_specifiers({"const"}, None, None, None, tag, None, _dummy_tok())
        assert t.base == "struct Foo"
        assert t.is_const

    def test_volatile_enum(self):
        p = _make_parser()
        tag = Type(base="enum Color", line=1, column=1)
        t = p._build_type_from_specifiers({"volatile"}, None, None, None, tag, None, _dummy_tok())
        assert t.base == "enum Color"
        assert t.is_volatile

    def test_const_volatile_union(self):
        p = _make_parser()
        tag = Type(base="union Data", line=1, column=1)
        t = p._build_type_from_specifiers({"const", "volatile"}, None, None, None, tag, None, _dummy_tok())
        assert t.is_const
        assert t.is_volatile


# ── typedef_name passthrough ─────────────────────────────────────────

class TestTypedefName:
    def test_typedef_passthrough(self):
        p = _make_parser()
        t = p._build_type_from_specifiers(set(), None, None, None, None, "size_t", _dummy_tok())
        assert t.base == "size_t"

    def test_const_typedef(self):
        p = _make_parser()
        t = p._build_type_from_specifiers({"const"}, None, None, None, None, "GLfloat", _dummy_tok())
        assert t.base == "GLfloat"
        assert t.is_const

    def test_volatile_typedef(self):
        p = _make_parser()
        t = p._build_type_from_specifiers({"volatile"}, None, None, None, None, "mytype", _dummy_tok())
        assert t.base == "mytype"
        assert t.is_volatile


# ── Error case ───────────────────────────────────────────────────────

class TestErrors:
    def test_nothing_set_raises(self):
        p = _make_parser()
        with pytest.raises(ParserError, match="Expected type specifier"):
            p._build_type_from_specifiers(set(), None, None, None, None, None, _dummy_tok())

    def test_bare_const_raises(self):
        """bare const with no type -> error (not implicit int)"""
        p = _make_parser()
        with pytest.raises(ParserError, match="Expected type specifier"):
            p._build_type_from_specifiers({"const"}, None, None, None, None, None, _dummy_tok())


# ── Source location propagation ──────────────────────────────────────

class TestSourceLocation:
    def test_line_column_from_start_tok(self):
        p = _make_parser()
        tok = _dummy_tok(line=42, col=7)
        t = p._build_type_from_specifiers(set(), None, None, "int", None, None, tok)
        assert t.line == 42
        assert t.column == 7

    def test_none_start_tok_defaults_to_zero(self):
        p = _make_parser()
        t = p._build_type_from_specifiers(set(), None, None, "int", None, None, None)
        assert t.line == 0
        assert t.column == 0
