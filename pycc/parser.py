"""pycc.parser

Recursive-descent parser for a practical C89/C99-ish subset.

This project originally planned a full C99 parser, but the repository currently
only contains lexer tests. To unblock end-to-end compilation for `examples/*.c`,
this parser focuses on:

- function definitions with `int` return type
- local/global `int` declarations (including simple arrays)
- statements: compound, if/else, while, for, do/while, return, break, continue
- expressions with C operator precedence for: assignment, ||, &&, bitwise, eq,
  rel, shift, add, mul, unary (+ - ! ~ & *), postfix calls and subscripts

It intentionally ignores preprocessor directives and most declaration
complexity (typedef/struct/union/enums). Those can be added iteratively.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple, Union, Set

from pycc.lexer import Token, TokenType
from pycc.ast_nodes import (
    Program,
    Type,
    Declaration,
    FunctionDecl,
    CompoundStmt,
    ExpressionStmt,
    IfStmt,
    WhileStmt,
    DoWhileStmt,
    ForStmt,
    SwitchStmt,
    CaseStmt,
    DefaultStmt,
    BreakStmt,
    ContinueStmt,
    ReturnStmt,
    DeclStmt,
    Identifier,
    IntLiteral,
    StringLiteral,
    CharLiteral,
    BinaryOp,
    UnaryOp,
    Assignment,
    FunctionCall,
    ArrayAccess,
    TernaryOp,
)


class ParserError(Exception):
    """Parser error"""
    def __init__(self, message: str, token: Optional[Token] = None):
        self.message = message
        self.token = token
        if token:
            super().__init__(f"{message} at {token.line}:{token.column}")
        else:
            super().__init__(message)


class Parser:
    """Parser for C99"""
    
    def __init__(self, tokens: List[Token]):
        # Filter out NEWLINE tokens to simplify parsing (lexer tracks position)
        self.tokens: List[Token] = [t for t in tokens if t.type != TokenType.NEWLINE]
        self.position = 0
        self.current_token: Optional[Token] = self.tokens[0] if self.tokens else None
    
    def parse(self) -> Program:
        """Parse entire program"""
        decls: List[Union[Declaration, FunctionDecl]] = []

        while not self._at(TokenType.EOF):
            # Skip stray semicolons
            if self._match(TokenType.SEMICOLON):
                continue

            decls.append(self._parse_external_declaration())

        # Use first token position for program location, default to 1:1
        if self.tokens:
            first = self.tokens[0]
            return Program(declarations=decls, line=first.line, column=first.column)
        return Program(declarations=decls, line=1, column=1)
    
    def advance(self) -> Token:
        """Move to next token"""
        if self.position < len(self.tokens) - 1:
            self.position += 1
            self.current_token = self.tokens[self.position]
        return self.current_token
    
    def peek(self, offset: int = 1) -> Optional[Token]:
        """Peek ahead"""
        pos = self.position + offset
        if pos < len(self.tokens):
            return self.tokens[pos]
        return None

    # -----------------
    # Helpers
    # -----------------

    def _at(self, t: TokenType) -> bool:
        return self.current_token is not None and self.current_token.type == t

    def _match(self, t: TokenType) -> bool:
        if self._at(t):
            self.advance()
            return True
        return False

    def _expect(self, t: TokenType, msg: str) -> Token:
        tok = self.current_token
        if tok is None or tok.type != t:
            raise ParserError(msg, tok)
        self.advance()
        return tok

    def _expect_keyword(self, kw: str, msg: str) -> Token:
        tok = self.current_token
        if tok is None or tok.type != TokenType.KEYWORD or tok.value != kw:
            raise ParserError(msg, tok)
        self.advance()
        return tok

    def _is_type_specifier(self) -> bool:
        return (
            self.current_token is not None
            and self.current_token.type == TokenType.KEYWORD
            and self.current_token.value in {"int", "void", "char"}
        )

    # -----------------
    # External decls
    # -----------------

    def _parse_external_declaration(self) -> Union[Declaration, FunctionDecl]:
        base_type = self._parse_type_specifier()
        name_tok = self._expect(TokenType.IDENTIFIER, "Expected identifier")

        # function or variable?
        if self._match(TokenType.LPAREN):
            params = self._parse_parameter_list()
            self._expect(TokenType.RPAREN, "Expected ')' after parameter list")

            # prototype
            if self._match(TokenType.SEMICOLON):
                return FunctionDecl(
                    name=name_tok.value,
                    return_type=base_type,
                    parameters=params,
                    body=None,
                    line=name_tok.line,
                    column=name_tok.column,
                )

            body = self._parse_compound_statement()
            return FunctionDecl(
                name=name_tok.value,
                return_type=base_type,
                parameters=params,
                body=body,
                line=name_tok.line,
                column=name_tok.column,
            )

        # variable (maybe array) with optional initializer
        decl = self._finish_declarator(base_type, name_tok)
        self._expect(TokenType.SEMICOLON, "Expected ';' after declaration")
        return decl

    def _parse_type_specifier(self) -> Type:
        tok = self.current_token
        if not self._is_type_specifier():
            raise ParserError("Expected type specifier", tok)
        self.advance()
        return Type(base=tok.value, line=tok.line, column=tok.column)

    def _parse_parameter_list(self) -> List[Declaration]:
        params: List[Declaration] = []
        if self._at(TokenType.RPAREN):
            return params
        # handle (void)
        if self.current_token and self.current_token.type == TokenType.KEYWORD and self.current_token.value == "void":
            void_tok = self.current_token
            self.advance()
            if self._at(TokenType.RPAREN):
                return []
            # otherwise treat as normal type
            base_type = Type(base="void", line=void_tok.line, column=void_tok.column)
            name_tok = self._expect(TokenType.IDENTIFIER, "Expected parameter name")
            params.append(Declaration(name=name_tok.value, type=base_type, line=name_tok.line, column=name_tok.column))
        else:
            while True:
                base_type = self._parse_type_specifier()
                name_tok = self._expect(TokenType.IDENTIFIER, "Expected parameter name")
                params.append(Declaration(name=name_tok.value, type=base_type, line=name_tok.line, column=name_tok.column))
                if not self._match(TokenType.COMMA):
                    break
        return params

    # -----------------
    # Statements
    # -----------------

    def _parse_compound_statement(self) -> CompoundStmt:
        lbrace = self._expect(TokenType.LBRACE, "Expected '{'")
        items: List[Union[Declaration, object]] = []
        while not self._at(TokenType.RBRACE):
            if self._at(TokenType.EOF):
                raise ParserError("Unterminated compound statement", self.current_token)
            if self._is_type_specifier():
                decl = self._parse_local_declaration()
                items.append(decl)
            else:
                items.append(self._parse_statement())
        self._expect(TokenType.RBRACE, "Expected '}'")
        return CompoundStmt(statements=items, line=lbrace.line, column=lbrace.column)

    def _parse_local_declaration(self) -> Declaration:
        base_type = self._parse_type_specifier()
        name_tok = self._expect(TokenType.IDENTIFIER, "Expected identifier")
        decl = self._finish_declarator(base_type, name_tok)
        self._expect(TokenType.SEMICOLON, "Expected ';' after declaration")
        return decl

    def _finish_declarator(self, base_type: Type, name_tok: Token) -> Declaration:
        ty = base_type
        # pointers (limited: consume leading '*'s)
        while self._match(TokenType.STAR):
            ty = Type(base=ty.base, is_pointer=True, line=ty.line, column=ty.column)

        initializer = None

        # array declarator: name[expr]
        array_size_val = None
        if self._match(TokenType.LBRACKET):
            size_expr = None
            if not self._at(TokenType.RBRACKET):
                size_expr = self._parse_expression()
            self._expect(TokenType.RBRACKET, "Expected ']' in array declarator")
            # If the size is a simple integer literal, record it on the declaration
            if isinstance(size_expr, IntLiteral):
                array_size_val = size_expr.value

        if self._match(TokenType.ASSIGN):
            initializer = self._parse_expression()

        return Declaration(
            name=name_tok.value,
            type=ty,
            initializer=initializer,
            line=name_tok.line,
            column=name_tok.column,
            array_size=array_size_val,
        )

    def _parse_statement(self):
        tok = self.current_token
        if tok is None:
            raise ParserError("Unexpected end of input")

        # compound
        if self._at(TokenType.LBRACE):
            return self._parse_compound_statement()

        # keywords
        if tok.type == TokenType.KEYWORD:
            kw = tok.value
            if kw == "return":
                self.advance()
                if self._match(TokenType.SEMICOLON):
                    return ReturnStmt(value=None, line=tok.line, column=tok.column)
                val = self._parse_expression()
                self._expect(TokenType.SEMICOLON, "Expected ';' after return")
                return ReturnStmt(value=val, line=tok.line, column=tok.column)
            if kw == "if":
                self.advance()
                self._expect(TokenType.LPAREN, "Expected '(' after if")
                cond = self._parse_expression()
                self._expect(TokenType.RPAREN, "Expected ')' after if condition")
                then_stmt = self._parse_statement()
                else_stmt = None
                if self.current_token and self.current_token.type == TokenType.KEYWORD and self.current_token.value == "else":
                    self.advance()
                    else_stmt = self._parse_statement()
                return IfStmt(condition=cond, then_stmt=then_stmt, else_stmt=else_stmt, line=tok.line, column=tok.column)
            if kw == "while":
                self.advance()
                self._expect(TokenType.LPAREN, "Expected '(' after while")
                cond = self._parse_expression()
                self._expect(TokenType.RPAREN, "Expected ')' after while condition")
                body = self._parse_statement()
                return WhileStmt(condition=cond, body=body, line=tok.line, column=tok.column)
            if kw == "do":
                self.advance()
                body = self._parse_statement()
                self._expect_keyword("while", "Expected 'while' after do body")
                self._expect(TokenType.LPAREN, "Expected '(' after while")
                cond = self._parse_expression()
                self._expect(TokenType.RPAREN, "Expected ')' after do-while condition")
                self._expect(TokenType.SEMICOLON, "Expected ';' after do-while")
                return DoWhileStmt(body=body, condition=cond, line=tok.line, column=tok.column)
            if kw == "for":
                self.advance()
                self._expect(TokenType.LPAREN, "Expected '(' after for")
                init = None
                if self._is_type_specifier():
                    init = self._parse_local_declaration()
                elif not self._at(TokenType.SEMICOLON):
                    init = self._parse_expression()
                    self._expect(TokenType.SEMICOLON, "Expected ';' after for init")
                else:
                    self._expect(TokenType.SEMICOLON, "Expected ';' after for init")

                cond = None
                if not self._at(TokenType.SEMICOLON):
                    cond = self._parse_expression()
                self._expect(TokenType.SEMICOLON, "Expected ';' after for condition")

                update = None
                if not self._at(TokenType.RPAREN):
                    update = self._parse_expression()
                self._expect(TokenType.RPAREN, "Expected ')' after for clauses")
                body = self._parse_statement()
                return ForStmt(init=init, condition=cond, update=update, body=body, line=tok.line, column=tok.column)
            if kw == "break":
                self.advance()
                self._expect(TokenType.SEMICOLON, "Expected ';' after break")
                return BreakStmt(line=tok.line, column=tok.column)
            if kw == "continue":
                self.advance()
                self._expect(TokenType.SEMICOLON, "Expected ';' after continue")
                return ContinueStmt(line=tok.line, column=tok.column)

        # expression statement
        if self._match(TokenType.SEMICOLON):
            return ExpressionStmt(expression=None, line=tok.line, column=tok.column)
        expr = self._parse_expression()
        self._expect(TokenType.SEMICOLON, "Expected ';' after expression")
        return ExpressionStmt(expression=expr, line=tok.line, column=tok.column)

    # -----------------
    # Expressions (precedence climbing)
    # -----------------

    def _parse_expression(self):
        return self._parse_assignment()

    def _parse_assignment(self):
        left = self._parse_conditional()
        if self.current_token and self.current_token.type in {
            TokenType.ASSIGN,
            TokenType.PLUS_ASSIGN,
            TokenType.MINUS_ASSIGN,
            TokenType.STAR_ASSIGN,
            TokenType.SLASH_ASSIGN,
            TokenType.PERCENT_ASSIGN,
            TokenType.LSHIFT_ASSIGN,
            TokenType.RSHIFT_ASSIGN,
            TokenType.AND_ASSIGN,
            TokenType.OR_ASSIGN,
            TokenType.XOR_ASSIGN,
        }:
            op_tok = self.current_token
            self.advance()
            right = self._parse_assignment()
            return Assignment(target=left, operator=op_tok.value, value=right, line=op_tok.line, column=op_tok.column)
        return left

    def _parse_conditional(self):
        expr = self._parse_logical_or()
        if self._match(TokenType.QUESTION):
            true_expr = self._parse_expression()
            self._expect(TokenType.COLON, "Expected ':' in conditional expression")
            false_expr = self._parse_conditional()
            return TernaryOp(condition=expr, true_expr=true_expr, false_expr=false_expr, line=expr.line, column=expr.column)
        return expr

    def _parse_logical_or(self):
        expr = self._parse_logical_and()
        while self.current_token and self.current_token.type == TokenType.LOR:
            op = self.current_token
            self.advance()
            rhs = self._parse_logical_and()
            expr = BinaryOp(operator=op.value, left=expr, right=rhs, line=op.line, column=op.column)
        return expr

    def _parse_logical_and(self):
        expr = self._parse_bitwise_or()
        while self.current_token and self.current_token.type == TokenType.LAND:
            op = self.current_token
            self.advance()
            rhs = self._parse_bitwise_or()
            expr = BinaryOp(operator=op.value, left=expr, right=rhs, line=op.line, column=op.column)
        return expr

    def _parse_bitwise_or(self):
        expr = self._parse_bitwise_xor()
        while self.current_token and self.current_token.type == TokenType.PIPE:
            op = self.current_token
            self.advance()
            rhs = self._parse_bitwise_xor()
            expr = BinaryOp(operator=op.value, left=expr, right=rhs, line=op.line, column=op.column)
        return expr

    def _parse_bitwise_xor(self):
        expr = self._parse_bitwise_and()
        while self.current_token and self.current_token.type == TokenType.CARET:
            op = self.current_token
            self.advance()
            rhs = self._parse_bitwise_and()
            expr = BinaryOp(operator=op.value, left=expr, right=rhs, line=op.line, column=op.column)
        return expr

    def _parse_bitwise_and(self):
        expr = self._parse_equality()
        while self.current_token and self.current_token.type == TokenType.AMPERSAND:
            op = self.current_token
            self.advance()
            rhs = self._parse_equality()
            expr = BinaryOp(operator=op.value, left=expr, right=rhs, line=op.line, column=op.column)
        return expr

    def _parse_equality(self):
        expr = self._parse_relational()
        while self.current_token and self.current_token.type in {TokenType.EQ, TokenType.NEQ}:
            op = self.current_token
            self.advance()
            rhs = self._parse_relational()
            expr = BinaryOp(operator=op.value, left=expr, right=rhs, line=op.line, column=op.column)
        return expr

    def _parse_relational(self):
        expr = self._parse_shift()
        while self.current_token and self.current_token.type in {TokenType.LT, TokenType.GT, TokenType.LTE, TokenType.GTE}:
            op = self.current_token
            self.advance()
            rhs = self._parse_shift()
            expr = BinaryOp(operator=op.value, left=expr, right=rhs, line=op.line, column=op.column)
        return expr

    def _parse_shift(self):
        expr = self._parse_additive()
        while self.current_token and self.current_token.type in {TokenType.LSHIFT, TokenType.RSHIFT}:
            op = self.current_token
            self.advance()
            rhs = self._parse_additive()
            expr = BinaryOp(operator=op.value, left=expr, right=rhs, line=op.line, column=op.column)
        return expr

    def _parse_additive(self):
        expr = self._parse_multiplicative()
        while self.current_token and self.current_token.type in {TokenType.PLUS, TokenType.MINUS}:
            op = self.current_token
            self.advance()
            rhs = self._parse_multiplicative()
            expr = BinaryOp(operator=op.value, left=expr, right=rhs, line=op.line, column=op.column)
        return expr

    def _parse_multiplicative(self):
        expr = self._parse_unary()
        while self.current_token and self.current_token.type in {TokenType.STAR, TokenType.SLASH, TokenType.PERCENT}:
            op = self.current_token
            self.advance()
            rhs = self._parse_unary()
            expr = BinaryOp(operator=op.value, left=expr, right=rhs, line=op.line, column=op.column)
        return expr

    def _parse_unary(self):
        tok = self.current_token
        if tok and tok.type in {TokenType.PLUS, TokenType.MINUS, TokenType.BANG, TokenType.TILDE, TokenType.AMPERSAND, TokenType.STAR}:
            self.advance()
            operand = self._parse_unary()
            return UnaryOp(operator=tok.value, operand=operand, is_postfix=False, line=tok.line, column=tok.column)
        return self._parse_postfix()

    def _parse_postfix(self):
        expr = self._parse_primary()
        while True:
            if self._match(TokenType.LPAREN):
                args: List = []
                if not self._at(TokenType.RPAREN):
                    args.append(self._parse_expression())
                    while self._match(TokenType.COMMA):
                        args.append(self._parse_expression())
                self._expect(TokenType.RPAREN, "Expected ')' after call")
                expr = FunctionCall(function=expr, arguments=args, line=expr.line, column=expr.column)
                continue
            if self._match(TokenType.LBRACKET):
                idx = self._parse_expression()
                self._expect(TokenType.RBRACKET, "Expected ']' after subscript")
                expr = ArrayAccess(array=expr, index=idx, line=expr.line, column=expr.column)
                continue
            break
        return expr

    def _parse_primary(self):
        tok = self.current_token
        if tok is None:
            raise ParserError("Unexpected end of input")

        if tok.type == TokenType.IDENTIFIER:
            self.advance()
            return Identifier(name=tok.value, line=tok.line, column=tok.column)
        if tok.type == TokenType.NUMBER:
            self.advance()
            # minimal integer-only parsing; float support later
            v = tok.value
            base = 10
            is_hex = False
            is_octal = False
            if v.startswith(("0x", "0X")):
                base = 16
                is_hex = True
            elif len(v) > 1 and v.startswith("0") and v[1].isdigit():
                base = 8
                is_octal = True
            # strip suffixes uUlL
            vv = v
            while vv and vv[-1] in "uUlL":
                vv = vv[:-1]
            value_int = int(vv, base)
            return IntLiteral(value=value_int, is_hex=is_hex, is_octal=is_octal, line=tok.line, column=tok.column)
        if tok.type == TokenType.STRING:
            self.advance()
            return StringLiteral(value=tok.value, line=tok.line, column=tok.column)
        if tok.type == TokenType.CHAR:
            self.advance()
            return CharLiteral(value=tok.value, line=tok.line, column=tok.column)
        if self._match(TokenType.LPAREN):
            expr = self._parse_expression()
            self._expect(TokenType.RPAREN, "Expected ')' ")
            return expr

        raise ParserError("Expected expression", tok)
