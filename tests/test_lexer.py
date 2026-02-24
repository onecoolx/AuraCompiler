"""
Unit tests for the Lexer module
"""

import pytest
from pycc.lexer import Lexer, Token, TokenType, LexerError


class TestLexerBasics:
    """Test basic lexer functionality"""
    
    def test_empty_input(self):
        """Test lexer with empty input"""
        lexer = Lexer("")
        tokens = lexer.tokenize()
        assert len(tokens) == 1
        assert tokens[0].type == TokenType.EOF
    
    def test_single_identifier(self):
        """Test lexing a single identifier"""
        lexer = Lexer("hello")
        tokens = lexer.tokenize()
        assert len(tokens) == 2
        assert tokens[0].type == TokenType.IDENTIFIER
        assert tokens[0].value == "hello"
        assert tokens[1].type == TokenType.EOF
    
    def test_multiple_identifiers(self):
        """Test lexing multiple identifiers"""
        lexer = Lexer("hello world foo")
        tokens = lexer.tokenize()
        assert len(tokens) == 4  # 3 identifiers + EOF
        assert all(t.type == TokenType.IDENTIFIER for t in tokens[:3])
        assert tokens[3].type == TokenType.EOF


class TestKeywords:
    """Test keyword recognition"""
    
    def test_if_keyword(self):
        """Test 'if' keyword"""
        lexer = Lexer("if")
        tokens = lexer.tokenize()
        assert tokens[0].type == TokenType.KEYWORD
        assert tokens[0].value == "if"
    
    def test_all_c99_keywords(self):
        """Test recognition of all C99 keywords"""
        keywords = "int float char void return if else while for do switch case"
        lexer = Lexer(keywords)
        tokens = lexer.tokenize()
        # Remove EOF
        tokens = tokens[:-1]
        assert len(tokens) == len(keywords.split())
        assert all(t.type == TokenType.KEYWORD for t in tokens)
    
    def test_keyword_vs_identifier(self):
        """Test keyword vs identifier distinction"""
        lexer = Lexer("int integer")
        tokens = lexer.tokenize()
        assert tokens[0].type == TokenType.KEYWORD
        assert tokens[0].value == "int"
        assert tokens[1].type == TokenType.IDENTIFIER
        assert tokens[1].value == "integer"


class TestNumbers:
    """Test number literal lexing"""
    
    def test_decimal_integer(self):
        """Test decimal integer"""
        lexer = Lexer("123")
        tokens = lexer.tokenize()
        assert tokens[0].type == TokenType.NUMBER
        assert tokens[0].value == "123"
    
    def test_octal_integer(self):
        """Test octal integer"""
        lexer = Lexer("0755")
        tokens = lexer.tokenize()
        assert tokens[0].type == TokenType.NUMBER
        assert tokens[0].value == "0755"
    
    def test_hex_integer(self):
        """Test hexadecimal integer"""
        lexer = Lexer("0xDEADBEEF")
        tokens = lexer.tokenize()
        assert tokens[0].type == TokenType.NUMBER
        assert tokens[0].value == "0xDEADBEEF"
    
    def test_float_literal(self):
        """Test float literal"""
        lexer = Lexer("3.14")
        tokens = lexer.tokenize()
        assert tokens[0].type == TokenType.NUMBER
        assert tokens[0].value == "3.14"
    
    def test_float_with_exponent(self):
        """Test float with exponent"""
        lexer = Lexer("1.0e-5")
        tokens = lexer.tokenize()
        assert tokens[0].type == TokenType.NUMBER
        assert tokens[0].value == "1.0e-5"
    
    def test_float_with_suffix(self):
        """Test float with suffix"""
        lexer = Lexer("3.14f")
        tokens = lexer.tokenize()
        assert tokens[0].type == TokenType.NUMBER
        assert tokens[0].value == "3.14f"
    
    def test_multiple_numbers(self):
        """Test multiple numbers"""
        lexer = Lexer("10 20 30")
        tokens = lexer.tokenize()
        assert len(tokens) == 4  # 3 numbers + EOF
        assert all(t.type == TokenType.NUMBER for t in tokens[:3])


class TestStrings:
    """Test string literal lexing"""
    
    def test_simple_string(self):
        """Test simple string"""
        lexer = Lexer('"hello"')
        tokens = lexer.tokenize()
        assert tokens[0].type == TokenType.STRING
        assert tokens[0].value == "hello"
    
    def test_string_with_spaces(self):
        """Test string with spaces"""
        lexer = Lexer('"hello world"')
        tokens = lexer.tokenize()
        assert tokens[0].type == TokenType.STRING
        assert tokens[0].value == "hello world"
    
    def test_string_with_escape(self):
        """Test string with escape sequences"""
        lexer = Lexer('"hello\\nworld"')
        tokens = lexer.tokenize()
        assert tokens[0].type == TokenType.STRING
        assert tokens[0].value == "hello\nworld"
    
    def test_string_with_tab(self):
        """Test string with tab escape"""
        lexer = Lexer('"hello\\tworld"')
        tokens = lexer.tokenize()
        assert tokens[0].type == TokenType.STRING
        assert tokens[0].value == "hello\tworld"
    
    def test_char_literal(self):
        """Test character literal"""
        lexer = Lexer("'a'")
        tokens = lexer.tokenize()
        assert tokens[0].type == TokenType.CHAR
        assert tokens[0].value == "a"


class TestOperators:
    """Test operator lexing"""
    
    def test_arithmetic_operators(self):
        """Test arithmetic operators"""
        lexer = Lexer("+ - * / %")
        tokens = lexer.tokenize()
        expected = [TokenType.PLUS, TokenType.MINUS, TokenType.STAR, 
                   TokenType.SLASH, TokenType.PERCENT]
        for i, exp_type in enumerate(expected):
            assert tokens[i].type == exp_type
    
    def test_comparison_operators(self):
        """Test comparison operators"""
        lexer = Lexer("== != < > <= >=")
        tokens = lexer.tokenize()
        expected = [TokenType.EQ, TokenType.NEQ, TokenType.LT, 
                   TokenType.GT, TokenType.LTE, TokenType.GTE]
        for i, exp_type in enumerate(expected):
            assert tokens[i].type == exp_type
    
    def test_logical_operators(self):
        """Test logical operators"""
        lexer = Lexer("&& || !")
        tokens = lexer.tokenize()
        expected = [TokenType.LAND, TokenType.LOR, TokenType.BANG]
        for i, exp_type in enumerate(expected):
            assert tokens[i].type == exp_type
    
    def test_bitwise_operators(self):
        """Test bitwise operators"""
        lexer = Lexer("& | ^ ~ << >>")
        tokens = lexer.tokenize()
        expected = [TokenType.AMPERSAND, TokenType.PIPE, TokenType.CARET,
                   TokenType.TILDE, TokenType.LSHIFT, TokenType.RSHIFT]
        for i, exp_type in enumerate(expected):
            assert tokens[i].type == exp_type
    
    def test_assignment_operators(self):
        """Test assignment operators"""
        lexer = Lexer("= += -= *= /= %=")
        tokens = lexer.tokenize()
        expected = [TokenType.ASSIGN, TokenType.PLUS_ASSIGN, TokenType.MINUS_ASSIGN,
                   TokenType.STAR_ASSIGN, TokenType.SLASH_ASSIGN, TokenType.PERCENT_ASSIGN]
        for i, exp_type in enumerate(expected):
            assert tokens[i].type == exp_type
    
    def test_increment_decrement(self):
        """Test increment and decrement operators"""
        lexer = Lexer("++ --")
        tokens = lexer.tokenize()
        assert tokens[0].type == TokenType.INCREMENT
        assert tokens[1].type == TokenType.DECREMENT
    
    def test_pointer_operators(self):
        """Test pointer-related operators"""
        lexer = Lexer("* & -> .")
        tokens = lexer.tokenize()
        expected = [TokenType.STAR, TokenType.AMPERSAND, TokenType.ARROW, TokenType.DOT]
        for i, exp_type in enumerate(expected):
            assert tokens[i].type == exp_type
    
    def test_ternary_operator(self):
        """Test ternary operator"""
        lexer = Lexer("? :")
        tokens = lexer.tokenize()
        assert tokens[0].type == TokenType.QUESTION
        assert tokens[1].type == TokenType.COLON


class TestDelimiters:
    """Test delimiter lexing"""
    
    def test_parentheses(self):
        """Test parentheses"""
        lexer = Lexer("( )")
        tokens = lexer.tokenize()
        assert tokens[0].type == TokenType.LPAREN
        assert tokens[1].type == TokenType.RPAREN
    
    def test_braces(self):
        """Test braces"""
        lexer = Lexer("{ }")
        tokens = lexer.tokenize()
        assert tokens[0].type == TokenType.LBRACE
        assert tokens[1].type == TokenType.RBRACE
    
    def test_brackets(self):
        """Test brackets"""
        lexer = Lexer("[ ]")
        tokens = lexer.tokenize()
        assert tokens[0].type == TokenType.LBRACKET
        assert tokens[1].type == TokenType.RBRACKET
    
    def test_semicolon_comma(self):
        """Test semicolon and comma"""
        lexer = Lexer("; ,")
        tokens = lexer.tokenize()
        assert tokens[0].type == TokenType.SEMICOLON
        assert tokens[1].type == TokenType.COMMA
    
    def test_ellipsis(self):
        """Test ellipsis"""
        lexer = Lexer("...")
        tokens = lexer.tokenize()
        assert tokens[0].type == TokenType.ELLIPSIS


class TestComments:
    """Test comment handling"""
    
    def test_single_line_comment(self):
        """Test single-line comment"""
        lexer = Lexer("int x; // comment")
        tokens = lexer.tokenize()
        # Comments should be skipped
        assert tokens[0].type == TokenType.KEYWORD
        assert tokens[1].type == TokenType.IDENTIFIER
        assert tokens[2].type == TokenType.SEMICOLON
    
    def test_multi_line_comment(self):
        """Test multi-line comment"""
        lexer = Lexer("int /* comment */ x;")
        tokens = lexer.tokenize()
        assert tokens[0].type == TokenType.KEYWORD
        assert tokens[1].type == TokenType.IDENTIFIER
        assert tokens[2].type == TokenType.SEMICOLON
    
    def test_nested_comment_attempt(self):
        """Test comment with nested comment-like text"""
        lexer = Lexer("/* /* nested */ */")
        tokens = lexer.tokenize()
        # First /* */ should close the comment
        # Remaining */ should cause error
        assert tokens[0].type == TokenType.EOF or tokens[0].type == TokenType.STAR


class TestComplexProgram:
    """Test lexing of complex C programs"""
    
    def test_simple_function(self):
        """Test lexing a simple function"""
        code = """
        int main() {
            return 0;
        }
        """
        lexer = Lexer(code)
        tokens = lexer.tokenize()
        assert not lexer.has_errors()
        
        # Check key tokens
        token_types = [t.type for t in tokens]
        assert TokenType.KEYWORD in token_types  # int
        assert TokenType.IDENTIFIER in token_types  # main
        assert TokenType.LPAREN in token_types
        assert TokenType.RPAREN in token_types
        assert TokenType.LBRACE in token_types
        assert TokenType.RBRACE in token_types
    
    def test_loop_and_array(self):
        """Test lexing loop with array access"""
        code = """
        for (int i = 0; i < 10; i++) {
            arr[i] = i * 2;
        }
        """
        lexer = Lexer(code)
        tokens = lexer.tokenize()
        assert not lexer.has_errors()


class TestErrorHandling:
    """Test error handling"""
    
    def test_unexpected_character(self):
        """Test handling of unexpected character"""
        lexer = Lexer("int x = 5 @;")
        tokens = lexer.tokenize()
        assert lexer.has_errors()
        assert len(lexer.get_errors()) > 0
    
    def test_unterminated_string(self):
        """Test unterminated string"""
        lexer = Lexer('"unterminated')
        tokens = lexer.tokenize()
        assert lexer.has_errors()


class TestLineAndColumn:
    """Test line and column tracking"""
    
    def test_single_line_position(self):
        """Test position tracking on single line"""
        lexer = Lexer("int x")
        tokens = lexer.tokenize()
        assert tokens[0].line == 1
        assert tokens[0].column == 1
        assert tokens[1].line == 1
    
    def test_multiline_position(self):
        """Test position tracking across multiple lines"""
        lexer = Lexer("int\nx")
        tokens = lexer.tokenize()
        assert tokens[0].line == 1
        assert tokens[1].line == 2
    
    def test_column_tracking(self):
        """Test column tracking"""
        lexer = Lexer("int x y")
        tokens = lexer.tokenize()
        # First token at column 1
        assert tokens[0].column == 1
        # Second token at column 5 (after "int " which is 4 chars)
        assert tokens[1].column == 5


class TestEdgeCases:
    """Test edge cases"""
    
    def test_zero_prefix(self):
        """Test numbers starting with zero"""
        lexer = Lexer("0 00 000")
        tokens = lexer.tokenize()
        assert tokens[0].value == "0"
    
    def test_identifier_with_underscores(self):
        """Test identifiers with underscores"""
        lexer = Lexer("_private __builtin __test123_")
        tokens = lexer.tokenize()
        assert tokens[0].value == "_private"
        assert tokens[1].value == "__builtin"
        assert tokens[2].value == "__test123_"
    
    def test_consecutive_operators(self):
        """Test consecutive operators"""
        lexer = Lexer("++i--i")
        tokens = lexer.tokenize()
        assert tokens[0].type == TokenType.INCREMENT
        assert tokens[1].type == TokenType.IDENTIFIER
        assert tokens[2].type == TokenType.DECREMENT
    
    def test_whitespace_handling(self):
        """Test various whitespace"""
        lexer = Lexer("int    x\t\ty")
        tokens = lexer.tokenize()
        # Whitespace should be skipped
        assert tokens[0].type == TokenType.KEYWORD
        assert tokens[1].type == TokenType.IDENTIFIER
        assert tokens[2].type == TokenType.IDENTIFIER


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
