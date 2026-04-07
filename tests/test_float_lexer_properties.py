"""Property tests: float literal lexical analysis (Property 22)."""
import pytest
from pycc.lexer import Lexer, TokenType


def test_decimal_float_is_number_float():
    tokens = Lexer("3.14").tokenize()
    assert tokens[0].type == TokenType.NUMBER_FLOAT


def test_exponent_float_is_number_float():
    tokens = Lexer("1.0e-5").tokenize()
    assert tokens[0].type == TokenType.NUMBER_FLOAT


def test_f_suffix_float_is_number_float():
    tokens = Lexer("3.14f").tokenize()
    assert tokens[0].type == TokenType.NUMBER_FLOAT


def test_integer_is_number():
    tokens = Lexer("42").tokenize()
    assert tokens[0].type == TokenType.NUMBER


def test_integer_with_L_suffix_is_number():
    tokens = Lexer("1L").tokenize()
    assert tokens[0].type == TokenType.NUMBER


def test_integer_with_U_suffix_is_number():
    tokens = Lexer("1U").tokenize()
    assert tokens[0].type == TokenType.NUMBER
