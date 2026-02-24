"""
Lexical Analyzer (Lexer) for C99 Compiler

Converts source code into a stream of tokens for the parser.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import List, Optional, Dict, Set
import re


class TokenType(Enum):
    """Token types for C99 lexer"""
    # Literals
    NUMBER = auto()
    CHAR = auto()
    STRING = auto()
    
    # Identifiers and Keywords
    IDENTIFIER = auto()
    KEYWORD = auto()
    
    # Operators
    PLUS = auto()                # +
    MINUS = auto()               # -
    STAR = auto()                # *
    SLASH = auto()               # /
    PERCENT = auto()             # %
    ASSIGN = auto()              # =
    PLUS_ASSIGN = auto()         # +=
    MINUS_ASSIGN = auto()        # -=
    STAR_ASSIGN = auto()         # *=
    SLASH_ASSIGN = auto()        # /=
    PERCENT_ASSIGN = auto()      # %=
    EQ = auto()                  # ==
    NEQ = auto()                 # !=
    LT = auto()                  # <
    GT = auto()                  # >
    LTE = auto()                 # <=
    GTE = auto()                 # >=
    LSHIFT = auto()              # <<
    RSHIFT = auto()              # >>
    LSHIFT_ASSIGN = auto()       # <<=
    RSHIFT_ASSIGN = auto()       # >>=
    AMPERSAND = auto()           # &
    PIPE = auto()                # |
    CARET = auto()               # ^
    TILDE = auto()               # ~
    AND_ASSIGN = auto()          # &=
    OR_ASSIGN = auto()           # |=
    XOR_ASSIGN = auto()          # ^=
    LAND = auto()                # &&
    LOR = auto()                 # ||
    BANG = auto()                # !
    QUESTION = auto()            # ?
    COLON = auto()               # :
    INCREMENT = auto()           # ++
    DECREMENT = auto()           # --
    ARROW = auto()               # ->
    DOT = auto()                 # .
    ELLIPSIS = auto()            # ...
    
    # Delimiters
    LPAREN = auto()              # (
    RPAREN = auto()              # )
    LBRACE = auto()              # {
    RBRACE = auto()              # }
    LBRACKET = auto()            # [
    RBRACKET = auto()            # ]
    SEMICOLON = auto()           # ;
    COMMA = auto()               # ,
    
    # Special
    EOF = auto()
    NEWLINE = auto()


@dataclass
class Token:
    """Represents a lexical token"""
    type: TokenType
    value: str
    line: int
    column: int
    
    def __repr__(self) -> str:
        return f"Token({self.type.name}, {repr(self.value)}, {self.line}:{self.column})"


class LexerError(Exception):
    """Lexer error with line and column information"""
    def __init__(self, message: str, line: int, column: int):
        self.message = message
        self.line = line
        self.column = column
        super().__init__(f"{message} at {line}:{column}")


class Lexer:
    """Lexical analyzer for C99 source code"""
    
    # C99 keywords
    KEYWORDS: Set[str] = {
        'auto', 'break', 'case', 'char', 'const', 'continue', 'default', 'do',
        'double', 'else', 'enum', 'extern', 'float', 'for', 'goto', 'if',
        'inline', 'int', 'long', 'register', 'restrict', 'return', 'short',
        'signed', 'sizeof', 'static', 'struct', 'switch', 'typedef', 'union',
        'unsigned', 'void', 'volatile', 'while', '_Bool', '_Complex', '_Imaginary',
        '_Pragma', '_Alignas', '_Alignof', '_Atomic', '_Generic', '_Noreturn',
        '_Static_assert', '_Thread_local'
    }
    
    def __init__(self, source: str, filename: str = "<input>"):
        """Initialize lexer with source code"""
        self.source = source
        self.filename = filename
        self.position = 0
        self.line = 1
        self.column = 1
        self.tokens: List[Token] = []
        self.errors: List[LexerError] = []
    
    def current_char(self) -> Optional[str]:
        """Get current character without consuming"""
        if self.position >= len(self.source):
            return None
        return self.source[self.position]
    
    def peek_char(self, offset: int = 1) -> Optional[str]:
        """Peek ahead at character"""
        pos = self.position + offset
        if pos >= len(self.source):
            return None
        return self.source[pos]
    
    def advance(self) -> Optional[str]:
        """Consume and return current character"""
        if self.position >= len(self.source):
            return None
        
        char = self.source[self.position]
        self.position += 1
        
        if char == '\n':
            self.line += 1
            self.column = 1
        else:
            self.column += 1
        
        return char
    
    def skip_whitespace(self) -> None:
        """Skip whitespace characters (except newline)"""
        while self.current_char() and self.current_char() in ' \t\r':
            self.advance()
    
    def skip_line_comment(self) -> None:
        """Skip single-line comment (//...)"""
        self.advance()  # skip first /
        self.advance()  # skip second /
        
        while self.current_char() and self.current_char() != '\n':
            self.advance()
    
    def skip_block_comment(self) -> None:
        """Skip multi-line comment (/* ... */)"""
        self.advance()  # skip /
        self.advance()  # skip *
        
        while self.current_char():
            if self.current_char() == '*' and self.peek_char() == '/':
                self.advance()  # skip *
                self.advance()  # skip /
                return
            self.advance()
        
        # Reached EOF without closing comment
        self.errors.append(LexerError("Unterminated block comment", self.line, self.column))
    
    def read_string(self) -> str:
        """Read string literal"""
        quote_char = self.current_char()
        self.advance()  # skip opening quote
        
        result = ""
        while self.current_char() and self.current_char() != quote_char:
            if self.current_char() == '\\':
                self.advance()
                next_char = self.current_char()
                if next_char is None:
                    self.errors.append(LexerError("Unterminated string", self.line, self.column))
                    break
                
                # Handle escape sequences
                escape_map = {
                    'n': '\n', 't': '\t', 'r': '\r', '\\': '\\',
                    '"': '"', "'": "'", '0': '\0', 'a': '\a',
                    'b': '\b', 'f': '\f', 'v': '\v'
                }
                if next_char in escape_map:
                    result += escape_map[next_char]
                elif next_char == 'x':
                    # Hex escape \xHH
                    self.advance()
                    hex_chars = ""
                    for _ in range(2):
                        if self.current_char() and self.current_char() in '0123456789abcdefABCDEF':
                            hex_chars += self.current_char()
                            self.advance()
                        else:
                            break
                    if hex_chars:
                        result += chr(int(hex_chars, 16))
                        continue
                    else:
                        result += 'x'
                        continue
                else:
                    result += next_char
                self.advance()
            else:
                result += self.current_char()
                self.advance()
        
        if self.current_char() == quote_char:
            self.advance()  # skip closing quote
        else:
            self.errors.append(LexerError("Unterminated string", self.line, self.column))
        
        return result
    
    def read_number(self) -> tuple[str, TokenType]:
        """Read number literal (integer or float)"""
        num_str = ""
        is_float = False
        
        # Handle hex, octal, or decimal
        if self.current_char() == '0' and self.peek_char() in 'xX':
            num_str += self.advance()  # 0
            num_str += self.advance()  # x
            while self.current_char() and self.current_char() in '0123456789abcdefABCDEF':
                num_str += self.advance()
            return (num_str, TokenType.NUMBER)
        
        if self.current_char() == '0' and self.peek_char() in '0123456789':
            # Octal number
            num_str += self.advance()  # 0
            while self.current_char() and self.current_char() in '01234567':
                num_str += self.advance()
            # Check if it continues as float
            if self.current_char() == '.':
                is_float = True
                num_str += self.advance()
                while self.current_char() and self.current_char() in '0123456789':
                    num_str += self.advance()
            
            if self.current_char() and self.current_char() in 'eE':
                is_float = True
                num_str += self.advance()
                if self.current_char() in '+-':
                    num_str += self.advance()
                while self.current_char() and self.current_char() in '0123456789':
                    num_str += self.advance()
            
            return (num_str, TokenType.NUMBER)
        
        # Decimal or float number
        while self.current_char() and self.current_char().isdigit():
            num_str += self.advance()
        
        # Check for decimal point
        if self.current_char() == '.' and self.peek_char() and self.peek_char().isdigit():
            is_float = True
            num_str += self.advance()  # .
            while self.current_char() and self.current_char().isdigit():
                num_str += self.advance()
        
        # Check for exponent
        if self.current_char() and self.current_char() in 'eE':
            is_float = True
            num_str += self.advance()
            if self.current_char() in '+-':
                num_str += self.advance()
            while self.current_char() and self.current_char().isdigit():
                num_str += self.advance()
        
        # Check for float suffix (f, F, l, L)
        if self.current_char() and self.current_char() in 'fFlL':
            is_float = True
            num_str += self.advance()
        
        # Check for integer suffix (u, U, l, L, ll, LL)
        while self.current_char() and self.current_char() in 'uUlL':
            num_str += self.advance()
        
        return (num_str, TokenType.NUMBER)
    
    def read_identifier(self) -> str:
        """Read identifier or keyword"""
        ident = ""
        while self.current_char() and (self.current_char().isalnum() or self.current_char() == '_'):
            ident += self.advance()
        return ident
    
    def tokenize(self) -> List[Token]:
        """Tokenize entire source code"""
        self.tokens = []
        self.errors = []
        
        while self.position < len(self.source):
            self.skip_whitespace()
            
            if self.position >= len(self.source):
                break
            
            # Save token start position
            token_line = self.line
            token_column = self.column
            
            char = self.current_char()
            # Preprocessor directive (#...) — skip the rest of the line
            if char == '#':
                # consume until newline or EOF
                while self.current_char() and self.current_char() != '\n':
                    self.advance()
                continue
            
            # Comments
            if char == '/' and self.peek_char() == '/':
                self.skip_line_comment()
                continue
            elif char == '/' and self.peek_char() == '*':
                self.skip_block_comment()
                continue
            
            # Newline
            elif char == '\n':
                # Advance line/column tracking but do not emit NEWLINE tokens.
                # Tests expect next real token to have updated line number.
                self.advance()
            
            # String literal
            elif char == '"':
                value = self.read_string()
                self.tokens.append(Token(TokenType.STRING, value, token_line, token_column))
            
            # Character literal
            elif char == "'":
                value = self.read_string()  # Reuse string reading logic
                self.tokens.append(Token(TokenType.CHAR, value, token_line, token_column))
            
            # Numbers
            elif char.isdigit():
                value, token_type = self.read_number()
                self.tokens.append(Token(token_type, value, token_line, token_column))
            
            # Identifiers and keywords
            elif char.isalpha() or char == '_':
                ident = self.read_identifier()
                if ident in self.KEYWORDS:
                    self.tokens.append(Token(TokenType.KEYWORD, ident, token_line, token_column))
                else:
                    self.tokens.append(Token(TokenType.IDENTIFIER, ident, token_line, token_column))
            
            # Operators and delimiters
            elif char == '+':
                self.advance()
                if self.current_char() == '+':
                    self.advance()
                    self.tokens.append(Token(TokenType.INCREMENT, '++', token_line, token_column))
                elif self.current_char() == '=':
                    self.advance()
                    self.tokens.append(Token(TokenType.PLUS_ASSIGN, '+=', token_line, token_column))
                else:
                    self.tokens.append(Token(TokenType.PLUS, '+', token_line, token_column))
            
            elif char == '-':
                self.advance()
                if self.current_char() == '-':
                    self.advance()
                    self.tokens.append(Token(TokenType.DECREMENT, '--', token_line, token_column))
                elif self.current_char() == '=':
                    self.advance()
                    self.tokens.append(Token(TokenType.MINUS_ASSIGN, '-=', token_line, token_column))
                elif self.current_char() == '>':
                    self.advance()
                    self.tokens.append(Token(TokenType.ARROW, '->', token_line, token_column))
                else:
                    self.tokens.append(Token(TokenType.MINUS, '-', token_line, token_column))
            
            elif char == '*':
                self.advance()
                if self.current_char() == '=':
                    self.advance()
                    self.tokens.append(Token(TokenType.STAR_ASSIGN, '*=', token_line, token_column))
                else:
                    self.tokens.append(Token(TokenType.STAR, '*', token_line, token_column))
            
            elif char == '/':
                self.advance()
                if self.current_char() == '=':
                    self.advance()
                    self.tokens.append(Token(TokenType.SLASH_ASSIGN, '/=', token_line, token_column))
                else:
                    self.tokens.append(Token(TokenType.SLASH, '/', token_line, token_column))
            
            elif char == '%':
                self.advance()
                if self.current_char() == '=':
                    self.advance()
                    self.tokens.append(Token(TokenType.PERCENT_ASSIGN, '%=', token_line, token_column))
                else:
                    self.tokens.append(Token(TokenType.PERCENT, '%', token_line, token_column))
            
            elif char == '=':
                self.advance()
                if self.current_char() == '=':
                    self.advance()
                    self.tokens.append(Token(TokenType.EQ, '==', token_line, token_column))
                else:
                    self.tokens.append(Token(TokenType.ASSIGN, '=', token_line, token_column))
            
            elif char == '!':
                self.advance()
                if self.current_char() == '=':
                    self.advance()
                    self.tokens.append(Token(TokenType.NEQ, '!=', token_line, token_column))
                else:
                    self.tokens.append(Token(TokenType.BANG, '!', token_line, token_column))
            
            elif char == '<':
                self.advance()
                if self.current_char() == '<':
                    self.advance()
                    if self.current_char() == '=':
                        self.advance()
                        self.tokens.append(Token(TokenType.LSHIFT_ASSIGN, '<<=', token_line, token_column))
                    else:
                        self.tokens.append(Token(TokenType.LSHIFT, '<<', token_line, token_column))
                elif self.current_char() == '=':
                    self.advance()
                    self.tokens.append(Token(TokenType.LTE, '<=', token_line, token_column))
                else:
                    self.tokens.append(Token(TokenType.LT, '<', token_line, token_column))
            
            elif char == '>':
                self.advance()
                if self.current_char() == '>':
                    self.advance()
                    if self.current_char() == '=':
                        self.advance()
                        self.tokens.append(Token(TokenType.RSHIFT_ASSIGN, '>>=', token_line, token_column))
                    else:
                        self.tokens.append(Token(TokenType.RSHIFT, '>>', token_line, token_column))
                elif self.current_char() == '=':
                    self.advance()
                    self.tokens.append(Token(TokenType.GTE, '>=', token_line, token_column))
                else:
                    self.tokens.append(Token(TokenType.GT, '>', token_line, token_column))
            
            elif char == '&':
                self.advance()
                if self.current_char() == '&':
                    self.advance()
                    self.tokens.append(Token(TokenType.LAND, '&&', token_line, token_column))
                elif self.current_char() == '=':
                    self.advance()
                    self.tokens.append(Token(TokenType.AND_ASSIGN, '&=', token_line, token_column))
                else:
                    self.tokens.append(Token(TokenType.AMPERSAND, '&', token_line, token_column))
            
            elif char == '|':
                self.advance()
                if self.current_char() == '|':
                    self.advance()
                    self.tokens.append(Token(TokenType.LOR, '||', token_line, token_column))
                elif self.current_char() == '=':
                    self.advance()
                    self.tokens.append(Token(TokenType.OR_ASSIGN, '|=', token_line, token_column))
                else:
                    self.tokens.append(Token(TokenType.PIPE, '|', token_line, token_column))
            
            elif char == '^':
                self.advance()
                if self.current_char() == '=':
                    self.advance()
                    self.tokens.append(Token(TokenType.XOR_ASSIGN, '^=', token_line, token_column))
                else:
                    self.tokens.append(Token(TokenType.CARET, '^', token_line, token_column))
            
            elif char == '~':
                self.advance()
                self.tokens.append(Token(TokenType.TILDE, '~', token_line, token_column))
            
            elif char == '?':
                self.advance()
                self.tokens.append(Token(TokenType.QUESTION, '?', token_line, token_column))
            
            elif char == ':':
                self.advance()
                self.tokens.append(Token(TokenType.COLON, ':', token_line, token_column))
            
            elif char == '.':
                self.advance()
                if self.current_char() == '.' and self.peek_char() == '.':
                    self.advance()  # second .
                    self.advance()  # third .
                    self.tokens.append(Token(TokenType.ELLIPSIS, '...', token_line, token_column))
                else:
                    self.tokens.append(Token(TokenType.DOT, '.', token_line, token_column))
            
            elif char == '(':
                self.advance()
                self.tokens.append(Token(TokenType.LPAREN, '(', token_line, token_column))
            
            elif char == ')':
                self.advance()
                self.tokens.append(Token(TokenType.RPAREN, ')', token_line, token_column))
            
            elif char == '{':
                self.advance()
                self.tokens.append(Token(TokenType.LBRACE, '{', token_line, token_column))
            
            elif char == '}':
                self.advance()
                self.tokens.append(Token(TokenType.RBRACE, '}', token_line, token_column))
            
            elif char == '[':
                self.advance()
                self.tokens.append(Token(TokenType.LBRACKET, '[', token_line, token_column))
            
            elif char == ']':
                self.advance()
                self.tokens.append(Token(TokenType.RBRACKET, ']', token_line, token_column))
            
            elif char == ';':
                self.advance()
                self.tokens.append(Token(TokenType.SEMICOLON, ';', token_line, token_column))
            
            elif char == ',':
                self.advance()
                self.tokens.append(Token(TokenType.COMMA, ',', token_line, token_column))
            
            else:
                self.errors.append(LexerError(f"Unexpected character '{char}'", token_line, token_column))
                self.advance()
        
        # Add EOF token
        self.tokens.append(Token(TokenType.EOF, '', self.line, self.column))
        
        return self.tokens
    
    def has_errors(self) -> bool:
        """Check if any lexer errors occurred"""
        return len(self.errors) > 0
    
    def get_errors(self) -> List[LexerError]:
        """Get all lexer errors"""
        return self.errors
