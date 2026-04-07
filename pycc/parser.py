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
from typing import List, Optional, Sequence, Tuple, Union, Set, Dict

from pycc.lexer import Token, TokenType
from pycc.ast_nodes import (
    Program,
    Type,
    TypedefDecl,
    Declaration,
    FunctionDecl,
    StructDecl,
    UnionDecl,
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
    GotoStmt,
    LabelStmt,
    DeclStmt,
    Identifier,
    IntLiteral,
    FloatLiteral,
    StringLiteral,
    CharLiteral,
    BinaryOp,
    UnaryOp,
    SizeOf,
    Assignment,
    FunctionCall,
    ArrayAccess,
    MemberAccess,
    PointerMemberAccess,
    TernaryOp,
    CommaOp,
    Cast,
    EnumDecl,
    Initializer,
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
        # track typedef names seen so far while parsing
        self._typedefs: Set[str] = set()
        # map for recent struct/union definitions: key "struct Tag"/"union Tag" -> member declarations
        self._tag_members: Dict[str, List[Declaration]] = {}
    
    def parse(self) -> Program:
        """Parse entire program"""
        decls: List[Union[Declaration, FunctionDecl]] = []

        # Some type specifiers (like enum definitions) enqueue extra top-level decls.
        self._pending_enum_decls: List[EnumDecl] = []

        while not self._at(TokenType.EOF):
            # Skip stray semicolons
            if self._match(TokenType.SEMICOLON):
                continue

            d = self._parse_external_declaration()
            if self._pending_enum_decls:
                decls.extend(self._pending_enum_decls)
                self._pending_enum_decls = []
            decls.append(d)

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
        if self.current_token is None:
            return False
        # allow storage-class specifier to appear before the type in top-level decls
        if self.current_token.type == TokenType.KEYWORD and self.current_token.value in {"extern", "static", "auto", "register"}:
            return True
        if self.current_token.type == TokenType.KEYWORD and self.current_token.value in {
            "int",
            "void",
            "char",
            "float",
            "double",
            "__builtin_va_list",
            "struct",
            "union",
            "enum",
            # integer/qualifier specifiers
            "short",
            "long",
            "signed",
            "unsigned",
            "const",
            "volatile",
        }:
            return True
        # typedef names may appear as identifiers serving as type specifiers
        if self.current_token.type == TokenType.IDENTIFIER and self.current_token.value in self._typedefs:
            return True
        return False

    # -----------------
    # External decls
    # -----------------

    def _parse_external_declaration(self) -> Union[Declaration, FunctionDecl]:
        storage_class: Optional[str] = None
        # storage-class-specifier (minimal): extern/static
        if (
            self.current_token
            and self.current_token.type == TokenType.KEYWORD
            and self.current_token.value in {"extern", "static"}
        ):
            storage_class = self.current_token.value
            self.advance()

        # handle 'typedef' at top-level
        if self.current_token and self.current_token.type == TokenType.KEYWORD and self.current_token.value == "typedef":
            self.advance()
            base_type = self._parse_type_specifier()
            while self._match(TokenType.STAR):
                if isinstance(base_type, Type):
                    base_type.pointer_level = int(getattr(base_type, "pointer_level", 0)) + 1
                    if not getattr(base_type, "pointer_quals", None):
                        base_type.pointer_quals = []
                    base_type.pointer_quals.insert(0, set())
                    base_type._normalize_pointer_state()
                else:
                    base_type = Type(base=getattr(base_type, "base", "int"), pointer_level=1, is_pointer=True, line=getattr(base_type, "line", 1), column=getattr(base_type, "column", 1))
            name_tok = self._expect(TokenType.IDENTIFIER, "Expected identifier for typedef")
            self._expect(TokenType.SEMICOLON, "Expected ';' after typedef")
            td = TypedefDecl(name=name_tok.value, type=base_type, line=name_tok.line, column=name_tok.column)
            # remember typedef name for subsequent parsing
            self._typedefs.add(td.name)
            return td

        base_type = self._parse_type_specifier()
        # If the declaration starts with qualifiers like `const`, and the
        # underlying type is a typedef-name, `_parse_type_specifier()` will
        # return the normalized base type and stop with the typedef-name
        # identifier still as the current token.
        # Example token stream:
        #   extern const __int32_t **foo(void);
        # After _parse_type_specifier(): base_type is "const int", current token
        # is IDENTIFIER "__int32_t".
        # Consume that typedef-name token so the declarator parsing sees `*`.
        if (
            self.current_token
            and self.current_token.type == TokenType.IDENTIFIER
            and self.current_token.value in self._typedefs
        ):
            self.advance()

        # handle pointer declarators like: `int *p;` or `struct S *p;`
        # NOTE: This stage models only a *subset* of pointer qualifiers.
        # - `const T *p` (pointee-const) is approximated by keeping `base_type.is_const=True`
        #   on the pointer Type.
        # - `T *const p` (const pointer) is represented as `ptr_is_const=True`.
        while True:
            if self._match(TokenType.STAR):
                if isinstance(base_type, Type):
                    base_type.pointer_level = int(getattr(base_type, "pointer_level", 0)) + 1
                    if not getattr(base_type, "pointer_quals", None):
                        base_type.pointer_quals = []
                    base_type.pointer_quals.insert(0, set())
                    base_type._normalize_pointer_state()
                else:
                    base_type = Type(
                        base=getattr(base_type, "base", "int"),
                        pointer_level=1,
                        is_pointer=True,
                        line=getattr(base_type, "line", 1),
                        column=getattr(base_type, "column", 1),
                    )
                continue
            # If we see `const` here (after consuming a `*`), treat it as applying
            # to the pointer itself (e.g. `T *const p`).
            if self._at(TokenType.KEYWORD) and self.current_token.value in {"const", "volatile", "restrict"}:
                # Qualifiers after '*' apply to the outermost pointer level.
                if isinstance(base_type, Type) and getattr(base_type, "pointer_level", 0) > 0:
                    if not getattr(base_type, "pointer_quals", None):
                        base_type.pointer_quals = [set()]
                    base_type.pointer_quals[0].add(self.current_token.value)
                    base_type._normalize_pointer_state()
                self.advance()
                continue
            break

        # If the type-specifier is a typedef-name, `_parse_type_specifier()`
        # stops at the IDENTIFIER and leaves the following `*` tokens to be
        # consumed as part of the declarator. System headers commonly use:
        #   extern const T **foo(void);
        # where `T` is a typedef-name.
        while True:
            if self._match(TokenType.STAR):
                if isinstance(base_type, Type):
                    base_type.pointer_level = int(getattr(base_type, "pointer_level", 0)) + 1
                    if not getattr(base_type, "pointer_quals", None):
                        base_type.pointer_quals = []
                    base_type.pointer_quals.insert(0, set())
                    base_type._normalize_pointer_state()
                else:
                    base_type = Type(
                        base=getattr(base_type, "base", "int"),
                        pointer_level=1,
                        is_pointer=True,
                        line=getattr(base_type, "line", 1),
                        column=getattr(base_type, "column", 1),
                    )
                continue
            if self._at(TokenType.KEYWORD) and self.current_token.value in {"const", "volatile", "restrict"}:
                if isinstance(base_type, Type) and getattr(base_type, "pointer_level", 0) > 0:
                    if not getattr(base_type, "pointer_quals", None):
                        base_type.pointer_quals = [set()]
                    base_type.pointer_quals[0].add(self.current_token.value)
                    base_type._normalize_pointer_state()
                self.advance()
                continue
            break
        # Support standalone tag declarations like: `struct S { ... };`
        if self._match(TokenType.SEMICOLON):
            if isinstance(base_type, Type) and (base_type.base.startswith("struct ") or base_type.base.startswith("union ")):
                kind, tag = base_type.base.split(" ", 1)
                members = self._tag_members.get(base_type.base)
                if kind == "struct":
                    return StructDecl(name=None if tag == "<anonymous>" else tag, members=members, line=base_type.line, column=base_type.column)
                return UnionDecl(name=None if tag == "<anonymous>" else tag, members=members, line=base_type.line, column=base_type.column)
            # fallback: ignore
            return Declaration(name="__tagdecl__", type=base_type, line=base_type.line, column=base_type.column)

        # Support parenthesized declarators at top-level:
        #   int (*get(void))(int) { ... }
        if self._match(TokenType.LPAREN):
            ptr_ty = base_type
            # Inside the parentheses we expect `*name` (possibly multiple `*`).
            while self._match(TokenType.STAR):
                if isinstance(ptr_ty, Type):
                    ptr_ty.pointer_level = int(getattr(ptr_ty, "pointer_level", 0)) + 1
                    if not getattr(ptr_ty, "pointer_quals", None):
                        ptr_ty.pointer_quals = []
                    ptr_ty.pointer_quals.insert(0, set())
                    ptr_ty._normalize_pointer_state()
                else:
                    ptr_ty = Type(base=getattr(ptr_ty, "base", "int"), pointer_level=1, is_pointer=True, line=getattr(ptr_ty, "line", 1), column=getattr(ptr_ty, "column", 1))
            name_tok = self._expect(TokenType.IDENTIFIER, "Expected identifier")

            # optional parameter list inside the parentheses: `(*name(void))`
            if self._match(TokenType.LPAREN):
                depth = 1
                while self.current_token and depth > 0:
                    if self._match(TokenType.LPAREN):
                        depth += 1
                        continue
                    if self._match(TokenType.RPAREN):
                        depth -= 1
                        continue
                    self.advance()
            self._expect(TokenType.RPAREN, "Expected ')' in declarator")

            # first parameter list belongs to the function itself
            self._expect(TokenType.LPAREN, "Expected '(' after function name")
            params = self._parse_parameter_list()
            self._expect(TokenType.RPAREN, "Expected ')' after parameter list")

            # optional second parameter list: function returns pointer-to-function
            if self._match(TokenType.LPAREN):
                depth = 1
                while self.current_token and depth > 0:
                    if self._match(TokenType.LPAREN):
                        depth += 1
                        continue
                    if self._match(TokenType.RPAREN):
                        depth -= 1
                        continue
                    self.advance()
                ptr_ty = Type(base=f"{ptr_ty.base} (*)()", is_pointer=True, pointer_level=max(1, int(getattr(ptr_ty, "pointer_level", 0) or 1)), line=ptr_ty.line, column=ptr_ty.column)
                ptr_ty._normalize_pointer_state()
                # Best-effort: preserve arity for function-pointer return types.
                try:
                    ptr_ty.fn_param_count = len(params)
                except Exception:
                    pass

            # prototype or definition
            if self._match(TokenType.SEMICOLON):
                return FunctionDecl(
                    name=name_tok.value,
                    return_type=ptr_ty,
                    parameters=params,
                    body=None,
                    storage_class=storage_class,
                    line=name_tok.line,
                    column=name_tok.column,
                )
            body = self._parse_compound_statement()
            return FunctionDecl(
                name=name_tok.value,
                return_type=ptr_ty,
                parameters=params,
                body=body,
                storage_class=storage_class,
                line=name_tok.line,
                column=name_tok.column,
            )

        name_tok = self._expect(TokenType.IDENTIFIER, "Expected identifier")

        # Allow multiple declarators for pointers, e.g. `char *const p` / `const char *const p`.
        # Capture pointer-level qualifiers like `const` here.
        if self._at(TokenType.KEYWORD) and self.current_token.value in {"const", "volatile", "restrict"}:
            if self.current_token.value == "const":
                base_type.is_const = True
            elif self.current_token.value == "volatile":
                base_type.is_volatile = True
            elif self.current_token.value == "restrict":
                base_type.is_restrict = True
            self.advance()

        # function or variable?
        if self._match(TokenType.LPAREN):
            # Old-style (K&R) function definition: `int f(a,b) int a; { ... }`
            # We detect it by checking whether the tokens inside (...) are a list of
            # identifiers (possibly empty), not a type-specifier.
            if not self._at(TokenType.RPAREN):
                # Lookahead: if the next token isn't a type specifier and it's an identifier,
                # treat this as potential K&R identifier list.
                if self.current_token.type == TokenType.IDENTIFIER and not self._is_type_specifier():
                    knr_names: List[Token] = []
                    knr_names.append(self._expect(TokenType.IDENTIFIER, "Expected parameter name"))
                    while self._match(TokenType.COMMA):
                        knr_names.append(self._expect(TokenType.IDENTIFIER, "Expected parameter name"))
                    self._expect(TokenType.RPAREN, "Expected ')' after parameter name list")

                    # Parse the K&R parameter declarations (a sequence of declarations ending
                    # right before the function body '{').
                    param_decl_map: dict[str, Type] = {}
                    seen_param_decl: set[str] = set()
                    while self.current_token and not self._at(TokenType.LBRACE):
                        if not self._is_type_specifier():
                            raise ParserError("Expected type specifier", self.current_token)
                        p_base = self._parse_type_specifier()
                        while self._match(TokenType.STAR):
                            if isinstance(p_base, Type):
                                p_base.pointer_level = int(getattr(p_base, "pointer_level", 0)) + 1
                                if not getattr(p_base, "pointer_quals", None):
                                    p_base.pointer_quals = []
                                p_base.pointer_quals.insert(0, set())
                                p_base._normalize_pointer_state()
                            else:
                                p_base = Type(base=getattr(p_base, "base", "int"), pointer_level=1, is_pointer=True, line=getattr(p_base, "line", 1), column=getattr(p_base, "column", 1))
                        p_name_tok = self._expect(TokenType.IDENTIFIER, "Expected identifier")
                        # K&R parameter declarations do not have initializers.
                        self._expect(TokenType.SEMICOLON, "Expected ';' after parameter declaration")
                        if p_name_tok.value in seen_param_decl:
                            # Keep going; semantics will surface a nicer error.
                            pass
                        seen_param_decl.add(p_name_tok.value)
                        param_decl_map[p_name_tok.value] = p_base

                    # Support optional semicolon between old-style header and the body,
                    # as commonly written in K&R examples:
                    #   int f(a) int a; { ... }
                    # Some token streams may have a stray ';' here depending on formatting.
                    if self._at(TokenType.SEMICOLON):
                        self.advance()

                    # Build parameter list in order. Undeclared params default to int.
                    params: List[Declaration] = []
                    for nt in knr_names:
                        p_ty = param_decl_map.get(nt.value)
                        if p_ty is None:
                            p_ty = Type(base="int", line=nt.line, column=nt.column)
                        params.append(Declaration(name=nt.value, type=p_ty, line=nt.line, column=nt.column))

                    # extra parameter declarations not in name list => parse-time error
                    extra = [n for n in param_decl_map.keys() if n not in {t.value for t in knr_names}]
                    if extra:
                        raise ParserError("K&R parameter declaration has no matching parameter name", self.current_token)

                    # Now parse function body (definition only for K&R in this subset)
                    body = self._parse_compound_statement()
                    return FunctionDecl(
                        name=name_tok.value,
                        return_type=base_type,
                        parameters=params,
                        body=body,
                        storage_class=storage_class,
                        line=name_tok.line,
                        column=name_tok.column,
                    )

            params = self._parse_parameter_list()
            # Be permissive: if our parameter parser stopped early, fast-forward
            # to the matching ')'. This allows us to accept many system-header
            # prototypes we don't fully model yet.
            if not self._match(TokenType.RPAREN):
                depth = 1
                while self.current_token and depth > 0:
                    if self._match(TokenType.LPAREN):
                        depth += 1
                        continue
                    if self._match(TokenType.RPAREN):
                        depth -= 1
                        continue
                    self.advance()
                if depth != 0:
                    raise ParserError("Expected ')' after parameter list", self.current_token)

            # prototype
            if self._match(TokenType.SEMICOLON):
                return FunctionDecl(
                    name=name_tok.value,
                    return_type=base_type,
                    parameters=params,
                    body=None,
                    storage_class=storage_class,
                    line=name_tok.line,
                    column=name_tok.column,
                )

            body = self._parse_compound_statement()
            return FunctionDecl(
                name=name_tok.value,
                return_type=base_type,
                parameters=params,
                body=body,
                storage_class=storage_class,
                line=name_tok.line,
                column=name_tok.column,
            )

        # variable (maybe array) with optional initializer
        decl = self._finish_declarator(base_type, name_tok)
        decl.storage_class = storage_class
        self._expect(TokenType.SEMICOLON, "Expected ';' after declaration")
        return decl

    def _parse_type_specifier(self) -> Type:
        tok = self.current_token
        if not self._is_type_specifier():
            raise ParserError("Expected type specifier", tok)
        # qualifiers and integer-size/sign specifiers (C89 subset)
        # We support combinations like:
        #   unsigned int
        #   unsigned
        #   signed char
        #   short
        #   long int
        #   const volatile unsigned long
        is_const = False
        is_volatile = False
        is_unsigned = False
        is_signed = False
        size_kw: Optional[str] = None  # 'short'|'long' (single long for now)
        saw_any = False
        while self.current_token and self.current_token.type == TokenType.KEYWORD:
            v = self.current_token.value
            if v == "const":
                is_const = True
                saw_any = True
                self.advance()
                continue
            if v == "volatile":
                is_volatile = True
                saw_any = True
                self.advance()
                continue
            if v == "unsigned":
                is_unsigned = True
                saw_any = True
                self.advance()
                continue
            if v == "signed":
                is_signed = True
                saw_any = True
                self.advance()
                continue
            if v in {"short", "long"}:
                size_kw = v
                saw_any = True
                self.advance()
                continue
            break

        # builtin + sized integer forms
        if self.current_token and self.current_token.type == TokenType.KEYWORD and self.current_token.value in {"int", "void", "char", "float", "double", "__builtin_va_list"}:
            base_tok = self.current_token
            self.advance()
            t = Type(base=base_tok.value, line=base_tok.line, column=base_tok.column)
            t.is_const = is_const
            t.is_volatile = is_volatile
            t.is_unsigned = is_unsigned
            t.is_signed = is_signed
            # Encode short/long in base string for now (type system is stringly-typed elsewhere)
            if base_tok.value == "int" and size_kw in {"short", "long"}:
                t.base = f"{size_kw} int"
            # Normalize unsigned/signed base strings for downstream string checks.
            if t.base == "int":
                if is_unsigned:
                    t.base = "unsigned int"
                elif is_signed:
                    t.base = "int"
            if t.base == "char":
                if is_unsigned:
                    t.base = "unsigned char"
                elif is_signed:
                    t.base = "char"
            if t.base == "short int":
                if is_unsigned:
                    t.base = "unsigned short"

            # GCC builtin type: keep the name so downstream can apply ABI-aware
            # lowering (e.g. when passing a va_list to libc on SysV AMD64).
            # Treat it as an opaque scalar type for most semantic checks.
            return t

        # forms like: 'unsigned' (=> unsigned int), 'long' (=> long int), etc.
        if saw_any:
            if tok is None:
                raise ParserError("Expected type specifier", tok)
            t = Type(base="int", line=tok.line, column=tok.column)
            t.is_const = is_const
            t.is_volatile = is_volatile
            t.is_unsigned = is_unsigned
            t.is_signed = is_signed
            if size_kw in {"short", "long"}:
                t.base = f"{size_kw} int"
            # Normalize for downstream string checks.
            if t.base == "int" and is_unsigned:
                t.base = "unsigned int"
            if t.base == "short int" and is_unsigned:
                t.base = "unsigned short"
            if t.base == "long int" and is_unsigned:
                t.base = "unsigned long"
            return t

        # enum type specifier: `enum Tag { A=1, B, ... }` / `enum Tag` / `enum { ... }`
        if tok.type == TokenType.KEYWORD and tok.value == "enum":
            self.advance()
            tag_tok = None
            if self.current_token and self.current_token.type == TokenType.IDENTIFIER:
                tag_tok = self.current_token
                self.advance()

            if self._match(TokenType.LBRACE):
                members: List[tuple[str, Optional[object]]] = []
                while not self._at(TokenType.RBRACE):
                    if self._at(TokenType.EOF):
                        raise ParserError("Unterminated enum list", self.current_token)
                    name_tok = self._expect(TokenType.IDENTIFIER, "Expected enumerator name")
                    value_expr = None
                    if self._match(TokenType.ASSIGN):
                        # In enum lists, commas separate enumerators; parse the
                        # explicit value as an assignment-expression.
                        value_expr = self._parse_assignment()
                    members.append((name_tok.value, value_expr))
                    if not self._match(TokenType.COMMA):
                        break
                # allow trailing comma
                self._match(TokenType.COMMA)
                self._expect(TokenType.RBRACE, "Expected '}' after enum list")

                # queue a top-level EnumDecl so semantics can register constants
                self._pending_enum_decls.append(
                    EnumDecl(
                        name=None if tag_tok is None else tag_tok.value,
                        enumerators=members,
                        line=tok.line,
                        column=tok.column,
                    )
                )

            tag_name = tag_tok.value if tag_tok else "<anonymous>"
            return Type(base=f"enum {tag_name}", line=tok.line, column=tok.column)

        # struct/union type specifier: `struct Tag { ... }` / `struct Tag` / `struct { ... }`
        if tok.type == TokenType.KEYWORD and tok.value in {"struct", "union"}:
            kind = tok.value
            self.advance()
            tag_tok = None
            if self.current_token and self.current_token.type == TokenType.IDENTIFIER:
                tag_tok = self.current_token
                self.advance()

            # optional member list
            members = None
            if self._match(TokenType.LBRACE):
                members = []
                while not self._at(TokenType.RBRACE):
                    if self._at(TokenType.EOF):
                        raise ParserError("Unterminated struct/union member list", self.current_token)
                    mem_ty = self._parse_type_specifier()

                    # Support pointer members in struct/union definitions, e.g.
                    #   struct S { void *p; };
                    while self._match(TokenType.STAR):
                        mem_ty = Type(base=mem_ty.base, is_pointer=True, line=mem_ty.line, column=mem_ty.column)

                    mem_name = self._expect(TokenType.IDENTIFIER, "Expected member name")

                    # Support simple fixed-size array members (subset):
                    #   int a[2];
                    # This is needed for many system headers (e.g. glibc's __fsid_t).
                    if self._match(TokenType.LBRACKET):
                        # Array members appear frequently in system headers.
                        # We support a permissive subset:
                        #   int a[2];
                        #   char b[];            (unknown size)
                        #   char c[EXPR];        (we ignore EXPR tokens)
                        #
                        # For now we discard the array extent in the AST/type.
                        # This is a parsing-compatibility feature.
                        depth = 1
                        while self.current_token and depth > 0:
                            if self._match(TokenType.RBRACKET):
                                depth -= 1
                                break
                            # Be robust if an expression contains nested brackets (rare here).
                            if self._match(TokenType.LBRACKET):
                                depth += 1
                                continue
                            # Otherwise consume tokens until we reach ']'.
                            self.advance()
                        if depth != 0:
                            raise ParserError("Expected ']' after array declarator", self.current_token)

                    # no bitfields in MVP members yet
                    self._expect(TokenType.SEMICOLON, "Expected ';' after member declaration")
                    members.append(Declaration(name=mem_name.value, type=mem_ty, line=mem_name.line, column=mem_name.column))
                self._expect(TokenType.RBRACE, "Expected '}' after struct/union members")

                # Remember members for named tags so outer declaration `struct T {...};`
                # can be materialized as a StructDecl/UnionDecl node.
                if tag_tok is not None:
                    self._tag_members[f"{kind} {tag_tok.value}"] = members

            # record a textual type name for now: e.g. "struct Point"
            tag_name = tag_tok.value if tag_tok else "<anonymous>"
            return Type(base=f"{kind} {tag_name}", line=tok.line, column=tok.column)

        # typedef-name as type specifier
        if tok.type == TokenType.IDENTIFIER and tok.value in self._typedefs:
            self.advance()
            return Type(base=tok.value, line=tok.line, column=tok.column)

        raise ParserError("Expected type specifier", tok)

    def _parse_parameter_list(self) -> List[Declaration]:
        params: List[Declaration] = []
        if self._at(TokenType.RPAREN):
            return params
        # Special-case `(void)` meaning no parameters.
        if self._at_keyword("void"):
            # Only treat as empty parameter list when the next token is ')'.
            nxt = self._peek_token()
            if nxt and nxt.type == TokenType.RPAREN:
                self.advance()
                return []

        while True:
            # varargs: `...,` appears after a comma in prototypes.
            if self.current_token and self.current_token.type == TokenType.ELLIPSIS:
                self.advance()
                # Stash a sentinel so later stages can mark the FunctionDecl as variadic.
                # We don't type-check varargs yet.
                params.append(Declaration(name="...", type=Type(base="int", line=0, column=0), line=0, column=0))
                break

            base_type = self._parse_type_specifier()
            while self._match(TokenType.STAR):
                base_type = Type(base=base_type.base, is_pointer=True, line=base_type.line, column=base_type.column)

            # Support parenthesized pointer declarators in parameters:
            #   int (*fp)(int)
            if self._match(TokenType.LPAREN):
                ptr_ty = base_type
                while self._match(TokenType.STAR):
                    ptr_ty = Type(base=ptr_ty.base, is_pointer=True, line=ptr_ty.line, column=ptr_ty.column)
                name_tok = self._expect(TokenType.IDENTIFIER, "Expected parameter name")
                self._expect(TokenType.RPAREN, "Expected ')' in parameter declarator")
                # consume trailing function parameter list
                if self._match(TokenType.LPAREN):
                    # Best-effort: parse parameter list so we can preserve arity.
                    try:
                        fp_params = self._parse_parameter_list()
                        fp_arity: Optional[int] = len([p for p in fp_params if getattr(p, "name", None) != "..."])
                    except Exception:
                        fp_arity = None
                        depth = 1
                        while self.current_token and depth > 0:
                            if self._match(TokenType.LPAREN):
                                depth += 1
                                continue
                            if self._match(TokenType.RPAREN):
                                depth -= 1
                                continue
                            self.advance()
                    self._expect(TokenType.RPAREN, "Expected ')' after parameter list")

                    ptr_ty = Type(base=f"{ptr_ty.base} (*)()", is_pointer=True, line=ptr_ty.line, column=ptr_ty.column)
                    try:
                        ptr_ty.fn_param_count = fp_arity
                    except Exception:
                        pass
                params.append(Declaration(name=name_tok.value, type=ptr_ty, line=name_tok.line, column=name_tok.column))
            else:
                # Allow unnamed parameters in prototypes (common in system headers).
                # Example: `int f(int);`
                if self.current_token and self.current_token.type == TokenType.IDENTIFIER:
                    name_tok = self.current_token
                    self.advance()
                    params.append(Declaration(name=name_tok.value, type=base_type, line=name_tok.line, column=name_tok.column))
                else:
                    params.append(Declaration(name=None, type=base_type, line=base_type.line, column=base_type.column))

            if not self._match(TokenType.COMMA):
                break
        return params

    def _peek_token(self) -> Optional[Token]:
        # Next token without consuming it.
        if self.position + 1 < len(self.tokens):
            return self.tokens[self.position + 1]
        return None

    def _at_keyword(self, kw: str) -> bool:
        return bool(
            self.current_token
            and self.current_token.type == TokenType.KEYWORD
            and self.current_token.value == kw
        )

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
        storage_class: Optional[str] = None

        # storage-class-specifier (C89 subset): auto/register/static/extern
        if (
            self.current_token
            and self.current_token.type == TokenType.KEYWORD
            and self.current_token.value in {"auto", "register", "static", "extern"}
        ):
            storage_class = self.current_token.value
            self.advance()

        # support local typedefs
        if self.current_token and self.current_token.type == TokenType.KEYWORD and self.current_token.value == "typedef":
            self.advance()
            base_type = self._parse_type_specifier()
            while self._match(TokenType.STAR):
                base_type = Type(base=base_type.base, is_pointer=True, line=base_type.line, column=base_type.column)
            name_tok = self._expect(TokenType.IDENTIFIER, "Expected identifier for typedef")
            self._expect(TokenType.SEMICOLON, "Expected ';' after typedef")
            return TypedefDecl(name=name_tok.value, type=base_type, line=name_tok.line, column=name_tok.column)

        base_type = self._parse_type_specifier()
        # Consume any leading '*' tokens that appear before the identifier.
        # This is common in declarations like `int **pp = ...;`.
        while self._match(TokenType.STAR):
            base_type.pointer_level = int(getattr(base_type, "pointer_level", 0)) + 1
            if not getattr(base_type, "pointer_quals", None):
                base_type.pointer_quals = []
            base_type.pointer_quals.insert(0, set())
            base_type._normalize_pointer_state()

            # Capture pointer-level qualifiers immediately after this '*', e.g.
            #   int * const p;
            #   int * volatile p;
            while self._at(TokenType.KEYWORD) and self.current_token.value in {"const", "volatile", "restrict"}:
                try:
                    if not getattr(base_type, "pointer_quals", None):
                        base_type.pointer_quals = [set()]
                    base_type.pointer_quals[0].add(self.current_token.value)
                    base_type._normalize_pointer_state()
                except Exception:
                    pass
                self.advance()

        # NOTE: Base-type qualifiers (e.g. `const int`) are already represented
        # on `Type.is_const/is_volatile/is_restrict`. Do NOT move them onto
        # pointer_quals: that would incorrectly turn `const int *p` into
        # `int *const p` (const-qualified pointer object).

        if self._match(TokenType.LPAREN):
            # parse inner pointer part: (*name)
            ptr_ty = base_type
            while self._match(TokenType.STAR):
                ptr_ty.pointer_level = int(getattr(ptr_ty, "pointer_level", 0)) + 1
                if not getattr(ptr_ty, "pointer_quals", None):
                    ptr_ty.pointer_quals = []
                ptr_ty.pointer_quals.insert(0, set())
                ptr_ty._normalize_pointer_state()
            name_tok = self._expect(TokenType.IDENTIFIER, "Expected identifier")
            # support array-of-function-pointer declarator: (*name[...])
            if self._match(TokenType.LBRACKET):
                size_expr = None
                if not self._at(TokenType.RBRACKET):
                    size_expr = self._parse_expression()
                self._expect(TokenType.RBRACKET, "Expected ']' in array declarator")
                # Record array size for this name; keep element type as pointer.
                array_size_val = size_expr.value if isinstance(size_expr, IntLiteral) else None
                self._expect(TokenType.RPAREN, "Expected ')' in declarator")
                decl = self._finish_declarator(ptr_ty, name_tok)
                decl.array_size = array_size_val
            else:
                self._expect(TokenType.RPAREN, "Expected ')' in declarator")
                decl = self._finish_declarator(ptr_ty, name_tok)
        else:
            name_tok = self._expect(TokenType.IDENTIFIER, "Expected identifier")
            decl = self._finish_declarator(base_type, name_tok)
        decl.storage_class = storage_class
        self._expect(TokenType.SEMICOLON, "Expected ';' after declaration")
        return decl

    def _finish_declarator(self, base_type: Type, name_tok: Token) -> Declaration:
        ty = base_type
        if hasattr(ty, "_normalize_pointer_state"):
            ty._normalize_pointer_state()
        # pointers: consume leading '*'s and attach qualifiers per level.
        # IMPORTANT: qualifiers belong to the pointer level they appear on.
        # Example:
        #   const int *p;      -> pointee const (innermost level)
        #   int * const p;     -> pointer-object const (outermost level)
        #   const int * const p; -> both
        while True:
            if self._match(TokenType.STAR):
                ty.pointer_level = int(getattr(ty, "pointer_level", 0)) + 1
                if not getattr(ty, "pointer_quals", None):
                    ty.pointer_quals = []
                # Insert a new *outermost* pointer level (closest to the declared name).
                ty.pointer_quals.insert(0, set())
                ty._normalize_pointer_state()
                # Capture pointer-level qualifiers immediately following this '*'.
                while self._at(TokenType.KEYWORD) and self.current_token.value in {"const", "volatile", "restrict"}:
                    try:
                        if not getattr(ty, "pointer_quals", None):
                            ty.pointer_quals = [set()]
                        ty.pointer_quals[0].add(self.current_token.value)
                        ty._normalize_pointer_state()
                    except Exception:
                        pass
                    self.advance()
                continue

            # Qualifiers that occur here (not after a '*') belong to the base type.
            if self._at(TokenType.KEYWORD) and self.current_token.value == "const":
                try:
                    ty.is_const = True
                except Exception:
                    pass
                self.advance()
                continue
            if self._at(TokenType.KEYWORD) and self.current_token.value == "volatile":
                try:
                    ty.is_volatile = True
                except Exception:
                    pass
                self.advance()
                continue
            if self._at(TokenType.KEYWORD) and self.current_token.value == "restrict":
                try:
                    ty.is_restrict = True
                except Exception:
                    pass
                self.advance()
                continue
            break

        # NOTE: Base-type qualifiers (e.g. `const int`) are represented on
        # `Type.is_const/is_volatile/is_restrict` and must NOT be migrated to
        # pointer_quals. Qualifiers in pointer_quals only represent
        # `* const/* volatile/* restrict` (i.e. qualifiers on the pointer object).

        # array declarator: name[expr]
        # NOTE: this parser milestone supports only a single array suffix.
        # Multi-dimensional arrays will be supported later once type and
        # initializer lowering can represent nested array shapes.
        array_size_val = None
        array_dims: List[Optional[int]] = []
        while self._match(TokenType.LBRACKET):
            size_expr = None
            if not self._at(TokenType.RBRACKET):
                size_expr = self._parse_expression()
            self._expect(TokenType.RBRACKET, "Expected ']' in array declarator")

            dim: Optional[int] = None
            if isinstance(size_expr, IntLiteral):
                dim = size_expr.value
            array_dims.append(dim)

        # Preserve backwards-compat: `array_size` is the *outermost* dim.
        # For omitted outer dimension (e.g. `int a[][4]`), leave as None.
        if not getattr(ty, "is_pointer", False) and array_dims:
            array_size_val = array_dims[0]

        # function declarator: name(params)
        # Minimal support for function pointer declarations where the type is a
        # pointer, but the declarator has a trailing parameter list.
        if self._match(TokenType.LPAREN):
            # Best-effort: extract arity by reusing the normal parameter-list parser.
            # This supports `(void)` as 0 parameters.
            try:
                params = self._parse_parameter_list()
                fn_arity: Optional[int] = len([p for p in params if getattr(p, "name", None) != "..."])
            except Exception:
                params = None
                fn_arity = None
                # If parsing fails for any reason, consume until matching ')'.
                depth = 1
                while self.current_token and depth > 0:
                    if self._match(TokenType.LPAREN):
                        depth += 1
                        continue
                    if self._match(TokenType.RPAREN):
                        depth -= 1
                        continue
                    self.advance()
            self._expect(TokenType.RPAREN, "Expected ')' after parameter list")

            # Represent as pointer-to-function in a lightweight way.
            if not ty.is_pointer:
                ty = Type(base=ty.base, is_pointer=True, pointer_level=1, line=ty.line, column=ty.column)
                ty._normalize_pointer_state()
            ty = Type(base=f"{ty.base} (*)()", is_pointer=True, pointer_level=max(1, int(getattr(ty, "pointer_level", 0) or 1)), line=ty.line, column=ty.column)
            ty._normalize_pointer_state()
            try:
                ty.fn_param_count = fn_arity
            except Exception:
                pass

        initializer = None

        if self._match(TokenType.ASSIGN):
            # Support brace initializer lists for C89 aggregates.
            if self._at(TokenType.LBRACE):
                initializer = self._parse_initializer()
            else:
                initializer = self._parse_expression()

        return Declaration(
            name=name_tok.value,
            type=ty,
            initializer=initializer,
            line=name_tok.line,
            column=name_tok.column,
            array_size=array_size_val,
            array_dims=array_dims if array_dims else None,
        )

    def _parse_initializer(self) -> Expression:
        """Parse an initializer.

        Supported now:
        - assignment-expression
        - initializer-list: '{' [initializer (',' initializer)*] [','] '}'

        Designated initializers are intentionally deferred.
        """

        # initializer-list
        if self._match(TokenType.LBRACE):
            elements: List[tuple[Optional[object], object]] = []
            # empty initializer list => zero-init
            if not self._at(TokenType.RBRACE):
                while True:
                    # No designators in this milestone.
                    val = self._parse_initializer()
                    elements.append((None, val))
                    if not self._match(TokenType.COMMA):
                        break
                    if self._at(TokenType.RBRACE):
                        break
            rbrace = self._expect(TokenType.RBRACE, "Expected '}' after initializer")
            return Initializer(elements=elements, line=rbrace.line, column=rbrace.column)

        # assignment-expression
        return self._parse_assignment()

    def _parse_statement(self):
        tok = self.current_token
        if tok is None:
            raise ParserError("Unexpected end of input")

        # label: statement
        if tok.type == TokenType.IDENTIFIER and self.peek() and self.peek().type == TokenType.COLON:
            name_tok = tok
            self.advance()  # ident
            self._expect(TokenType.COLON, "Expected ':' after label")
            stmt = self._parse_statement()
            return LabelStmt(name=name_tok.value, statement=stmt, line=name_tok.line, column=name_tok.column)

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
            if kw == "goto":
                self.advance()
                lab = self._expect(TokenType.IDENTIFIER, "Expected label name after goto")
                self._expect(TokenType.SEMICOLON, "Expected ';' after goto")
                return GotoStmt(label=lab.value, line=tok.line, column=tok.column)
            if kw == "continue":
                self.advance()
                self._expect(TokenType.SEMICOLON, "Expected ';' after continue")
                return ContinueStmt(line=tok.line, column=tok.column)
            if kw == "switch":
                self.advance()
                self._expect(TokenType.LPAREN, "Expected '(' after switch")
                expr = self._parse_expression()
                self._expect(TokenType.RPAREN, "Expected ')' after switch expression")
                body = self._parse_statement()
                return SwitchStmt(expression=expr, body=body, line=tok.line, column=tok.column)
            if kw == "case":
                self.advance()
                val = self._parse_expression()
                self._expect(TokenType.COLON, "Expected ':' after case expression")
                stmt = self._parse_statement()
                return CaseStmt(value=val, statement=stmt, line=tok.line, column=tok.column)
            if kw == "default":
                self.advance()
                self._expect(TokenType.COLON, "Expected ':' after default")
                stmt = self._parse_statement()
                return DefaultStmt(statement=stmt, line=tok.line, column=tok.column)

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
        # C comma operator has the lowest precedence.
        expr = self._parse_assignment()
        while self.current_token and self.current_token.type == TokenType.COMMA:
            comma_tok = self.current_token
            self.advance()
            rhs = self._parse_assignment()
            expr = CommaOp(left=expr, right=rhs, line=comma_tok.line, column=comma_tok.column)
        return expr

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
        if tok and tok.type == TokenType.KEYWORD and tok.value == "sizeof":
            self.advance()
            # sizeof(type-name) or sizeof unary-expression
            if self._match(TokenType.LPAREN):
                if self._is_type_specifier():
                    ty = self._parse_type_specifier()
                    while self._match(TokenType.STAR):
                        ty.pointer_level = int(getattr(ty, "pointer_level", 0)) + 1
                        if not getattr(ty, "pointer_quals", None):
                            ty.pointer_quals = []
                        ty.pointer_quals.insert(0, set())
                        ty._normalize_pointer_state()
                    self._expect(TokenType.RPAREN, "Expected ')' after sizeof(type)")
                    return SizeOf(operand=None, type=ty, line=tok.line, column=tok.column)
                expr = self._parse_expression()
                self._expect(TokenType.RPAREN, "Expected ')' after sizeof expression")
                return SizeOf(operand=expr, type=None, line=tok.line, column=tok.column)
            operand = self._parse_unary()
            return SizeOf(operand=operand, type=None, line=tok.line, column=tok.column)
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
                    # In argument lists, commas separate arguments, so we must
                    # parse each argument as an assignment-expression.
                    args.append(self._parse_assignment())
                    while self._match(TokenType.COMMA):
                        args.append(self._parse_assignment())
                self._expect(TokenType.RPAREN, "Expected ')' after call")
                expr = FunctionCall(function=expr, arguments=args, line=expr.line, column=expr.column)
                continue
            if self._match(TokenType.LBRACKET):
                idx = self._parse_expression()
                self._expect(TokenType.RBRACKET, "Expected ']' after subscript")
                expr = ArrayAccess(array=expr, index=idx, line=expr.line, column=expr.column)
                continue
            if self._match(TokenType.DOT):
                mem = self._expect(TokenType.IDENTIFIER, "Expected member name after '.'")
                expr = MemberAccess(object=expr, member=mem.value, line=mem.line, column=mem.column)
                continue
            if self._match(TokenType.ARROW):
                mem = self._expect(TokenType.IDENTIFIER, "Expected member name after '->'")
                expr = PointerMemberAccess(pointer=expr, member=mem.value, line=mem.line, column=mem.column)
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
            # strip integer suffixes (uUlL). The lexer currently tokenizes e.g.
            # "1U" as a NUMBER token with value "1" followed by IDENTIFIER "U"
            # in some cases. Treat a trailing identifier consisting only of
            # [uUlL]+ as part of the numeric literal.
            if self.current_token and self.current_token.type == TokenType.IDENTIFIER:
                suf = self.current_token.value
                if suf and all(c in "uUlL" for c in suf):
                    v = v + suf
                    self.advance()
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
        if tok.type == TokenType.NUMBER_FLOAT:
            self.advance()
            v = tok.value
            # Strip float suffix
            suffix = ''
            if v and v[-1] in 'fFlL':
                suffix = v[-1]
                v = v[:-1]
            value_float = float(v)
            return FloatLiteral(value=value_float, suffix=suffix, line=tok.line, column=tok.column)
        if tok.type == TokenType.STRING:
            self.advance()
            return StringLiteral(value=tok.value, line=tok.line, column=tok.column)
        if tok.type == TokenType.CHAR:
            self.advance()
            return CharLiteral(value=tok.value, line=tok.line, column=tok.column)
        if self._match(TokenType.LPAREN):
            # Either (expression) or (type-name) cast.
            if self._is_type_specifier():
                ty = self._parse_type_specifier()
                while self._match(TokenType.STAR):
                    ty.pointer_level = int(getattr(ty, "pointer_level", 0)) + 1
                    if not getattr(ty, "pointer_quals", None):
                        ty.pointer_quals = []
                    ty.pointer_quals.insert(0, set())
                    ty._normalize_pointer_state()
                self._expect(TokenType.RPAREN, "Expected ')' after cast type")
                expr = self._parse_unary()
                return Cast(type=ty, expression=expr, line=tok.line, column=tok.column)
            expr = self._parse_expression()
            self._expect(TokenType.RPAREN, "Expected ')' ")
            return expr

        raise ParserError("Expected expression", tok)
