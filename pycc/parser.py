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

from dataclasses import dataclass, field
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
    Designator,
)


@dataclass
class DeclaratorInfo:
    """Result of parsing a C declarator.

    Captures all information from the declarator portion of a C declaration:
    pointer prefixes, the declared name, array suffixes, and function parameter
    suffixes.  This is a pure data container — it does NOT hold the base type
    (that comes from the declaration-specifiers parsed separately).

    Grammar (C89 §6.5.4 / C99 §6.7.5):
        declarator          = pointer? direct-declarator
        pointer             = '*' type-qualifier-list? pointer?
        direct-declarator   = identifier
                            | '(' declarator ')'
                            | direct-declarator '[' constant-expr? ']'
                            | direct-declarator '(' parameter-list ')'
    """
    name: Optional[str] = None
    name_tok: Optional[Token] = None
    pointer_level: int = 0
    pointer_quals: List[Set[str]] = field(default_factory=list)
    array_dims: List[Optional[int]] = field(default_factory=list)
    is_function: bool = False
    fn_params: Optional[List] = None
    fn_is_variadic: bool = False
    is_paren_wrapped: bool = False
    outer_pointer_level: int = 0  # pointer levels outside parentheses


def _build_array_type(base_type: Type, dims: List[Optional[int]]) -> Type:
    """Construct an array Type from a base element type and dimension list.

    For ``int arr[3][4]`` with base_type=Type(base="int") and dims=[3,4],
    the result is::

        Type(base="int", is_array=True,
             array_element_type=Type(base="int", is_array=True,
                 array_element_type=Type(base="int"),
                 array_dimensions=[4]),
             array_dimensions=[3, 4])

    The innermost element type preserves the base_type's qualifiers (pointer,
    const, etc.) but strips any existing array markers.
    """
    if not dims:
        return base_type

    # Build the leaf element type — a copy of base_type without array fields.
    elem = Type(
        base=base_type.base,
        is_pointer=base_type.is_pointer,
        pointer_level=base_type.pointer_level,
        is_const=base_type.is_const,
        is_volatile=base_type.is_volatile,
        is_restrict=base_type.is_restrict,
        is_unsigned=base_type.is_unsigned,
        is_signed=base_type.is_signed,
        ptr_is_const=base_type.ptr_is_const,
        ptr_is_volatile=base_type.ptr_is_volatile,
        ptr_is_restrict=base_type.ptr_is_restrict,
        pointer_quals=list(base_type.pointer_quals) if base_type.pointer_quals else [],
        fn_param_count=base_type.fn_param_count,
        fn_param_types=base_type.fn_param_types,
        fn_return_type=base_type.fn_return_type,
        line=base_type.line,
        column=base_type.column,
    )

    # Build from innermost dimension outward.
    result = elem
    for dim in reversed(dims[1:]):
        result = Type(
            base=base_type.base,
            is_pointer=base_type.is_pointer,
            pointer_level=base_type.pointer_level,
            is_array=True,
            array_element_type=result,
            array_dimensions=[dim],
            line=base_type.line,
            column=base_type.column,
        )

    # Outermost layer carries the full dimensions list.
    return Type(
        base=base_type.base,
        is_pointer=base_type.is_pointer,
        pointer_level=base_type.pointer_level,
        is_array=True,
        array_element_type=result,
        array_dimensions=list(dims),
        line=base_type.line,
        column=base_type.column,
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
        # map typedef name -> underlying Type for sizeof evaluation at parse time
        self._typedef_types: Dict[str, Type] = {}
        # map for recent struct/union definitions: key "struct Tag"/"union Tag" -> member declarations
        self._tag_members: Dict[str, List[Declaration]] = {}
        # counter for generating unique synthetic tags for anonymous nested
        # struct/union definitions (e.g. `struct S { union { int a; float b; } u; }`)
        self._anon_tag_counter: int = 0
    
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
            if isinstance(d, list):
                decls.extend(d)
            else:
                decls.append(d)

        # Use first token position for program location, default to 1:1
        if self.tokens:
            first = self.tokens[0]
            prog = Program(declarations=decls, line=first.line, column=first.column)
        else:
            prog = Program(declarations=decls, line=1, column=1)
        # Attach all struct/union tag definitions discovered during parsing
        # so that semantic analysis can register layouts for inline-defined
        # structs that don't have standalone StructDecl nodes in the AST.
        prog._tag_members = dict(self._tag_members)
        return prog
    
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

    # Helpers

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
        if self.current_token.type == TokenType.KEYWORD and self.current_token.value in {"extern", "static", "auto", "register", "typedef"}:
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

    # External decls

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

        # C99 function specifier: 'inline' — accept and ignore
        if (
            self.current_token
            and self.current_token.type == TokenType.KEYWORD
            and self.current_token.value == "inline"
        ):
            self.advance()

        # handle 'typedef' at top-level
        if self.current_token and self.current_token.type == TokenType.KEYWORD and self.current_token.value == "typedef":
            self.advance()
            base_type = self._parse_type_specifier()

            # Use unified _parse_declarator for the first typedef declarator.
            decl_info = self._parse_declarator()
            td = self._build_typedef_decl(base_type, decl_info)
            self._typedefs.add(td.name)
            self._typedef_types[td.name] = td.type
            results = [td]

            # Multi-name typedef: typedef struct _XOC *XOC, *XFontSet;
            while self._match(TokenType.COMMA):
                extra_info = self._parse_declarator()
                etd = self._build_typedef_decl(base_type, extra_info)
                self._typedefs.add(etd.name)
                self._typedef_types[etd.name] = etd.type
                results.append(etd)

            self._expect(TokenType.SEMICOLON, "Expected ';' after typedef")
            # If the typedef involves a named struct/union with members, also emit a StructDecl
            b = getattr(base_type, 'base', '')
            if isinstance(b, str) and (b.startswith("struct ") or b.startswith("union ")):
                tag_key = b
                members = self._tag_members.get(tag_key)
                if members is not None:
                    kind, tag = b.split(" ", 1)
                    if kind == "struct":
                        sd = StructDecl(name=tag, members=members, line=base_type.line, column=base_type.column)
                    else:
                        sd = UnionDecl(name=tag, members=members, line=base_type.line, column=base_type.column)
                    return [sd] + results
            if len(results) == 1:
                return results[0]
            return results

        # C89 §6.7.1: implicit int return type — if the current token is an
        # identifier (not a type specifier) followed by '(', treat as a
        # function definition/declaration with implicit 'int' return type.
        if (
            not self._is_type_specifier()
            and self.current_token
            and self.current_token.type == TokenType.IDENTIFIER
            and self.peek(1)
            and self.peek(1).type == TokenType.LPAREN
        ):
            base_type = Type(base="int", line=self.current_token.line, column=self.current_token.column)
        else:
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

        # Support standalone tag declarations like: `struct S { ... };`
        # Check before _parse_declarator since there is no declarator here.
        if self._match(TokenType.SEMICOLON):
            if isinstance(base_type, Type) and (base_type.base.startswith("struct ") or base_type.base.startswith("union ")):
                kind, tag = base_type.base.split(" ", 1)
                members = self._tag_members.get(base_type.base)
                if kind == "struct":
                    return StructDecl(name=None if tag == "<anonymous>" else tag, members=members, line=base_type.line, column=base_type.column)
                return UnionDecl(name=None if tag == "<anonymous>" else tag, members=members, line=base_type.line, column=base_type.column)
            # fallback: ignore
            return Declaration(name="__tagdecl__", type=base_type, line=base_type.line, column=base_type.column)

        # --- K&R function definition detection ---
        # Old-style (K&R) function definition: `int f(a,b) int a; { ... }`
        # Detect by lookahead: IDENT '(' IDENT where inner IDENT is not a
        # type specifier.  Must be checked before _parse_declarator because
        # _parse_declarator_suffixes would try to parse the identifier list
        # as a parameter list and fail.
        if (self._at(TokenType.IDENTIFIER)
            and self.peek(1) and self.peek(1).type == TokenType.LPAREN
            and self.peek(2) and self.peek(2).type == TokenType.IDENTIFIER
            and self.peek(2).value not in self._typedefs
            and not (self.peek(2).type == TokenType.KEYWORD)
        ):
            # Check if the identifier inside parens is NOT a type specifier.
            # Save position to peek at the inner token.
            inner_tok = self.peek(2)
            _KNR_TYPE_KEYWORDS = {
                "int", "void", "char", "float", "double", "short", "long",
                "signed", "unsigned", "const", "volatile", "struct", "union",
                "enum", "__builtin_va_list",
            }
            if (inner_tok.value not in _KNR_TYPE_KEYWORDS
                and inner_tok.value not in self._typedefs):
                # This looks like K&R.  Parse it with the existing K&R path.
                name_tok = self._expect(TokenType.IDENTIFIER, "Expected identifier")
                self._expect(TokenType.LPAREN, "Expected '('")
                return self._parse_knr_function(name_tok, base_type, storage_class)

        # --- Unified declarator parsing ---
        # Use _parse_declarator to handle all declarator forms:
        #   int *p;              (pointer variable)
        #   int (*fp)(int);      (function pointer variable)
        #   int (*func(void))(int) { ... }  (function returning pointer)
        #   int func(int x) { ... }         (simple function)
        #   int a, b, c;         (multi-declarator)
        #   int (func)(int x);   (parenthesized function name)
        decl_info = self._parse_declarator()
        name_tok = decl_info.name_tok

        # Apply pointer levels from the declarator to the base type.
        ty = self._apply_declarator(base_type, decl_info)

        # --- Determine: function vs variable ---
        # A declarator with is_function=True can be either:
        #   (a) A real function definition/declaration: int func(int x);
        #   (b) A function pointer variable: int (*fp)(int);
        #   (c) A function pointer array: void (*table[])(int);
        #   (d) A function returning pointer: int (*func(void))(int) { ... }
        #
        # For (b) and (c), the function suffix (int) was consumed by
        # _parse_declarator as an outer suffix, so the next token is
        # '=', ';', ',', or '['.
        # For (d), the outer (int) was NOT consumed (inner suffix already
        # set is_function), so the next token is '('.
        # For (a), the next token is ';' or '{'.
        #
        # We route to the function path only when the declarator represents
        # a real function, not a function pointer variable.
        _is_real_function = decl_info.is_function
        if _is_real_function and decl_info.is_paren_wrapped and decl_info.pointer_level > 0:
            # Distinguish function pointer variable from function returning
            # pointer.  When ALL pointer levels come from outside the
            # parentheses (outer_pointer_level == pointer_level), the '*'
            # belongs to the return type: `char *(func)(params)` is a
            # function returning `char *`.  When some pointer levels are
            # inside the parentheses (outer < total), it is a function
            # pointer variable: `int (*fp)(params)`.
            inner_ptr = decl_info.pointer_level - decl_info.outer_pointer_level
            if inner_ptr > 0:
                # Has inner pointer — function pointer variable.
                if self._at(TokenType.ASSIGN) or self._at(TokenType.SEMICOLON) or self._at(TokenType.COMMA) or self._at(TokenType.LBRACKET):
                    _is_real_function = False

        if _is_real_function:
            # Function declaration or definition.
            params = decl_info.fn_params if decl_info.fn_params is not None else []

            # If the declarator was paren-wrapped with a pointer (e.g.
            # `int (*func(void))(int)`), the trailing `(int)` describes the
            # return type's function pointer signature.  _parse_declarator
            # only consumed the inner `(void)` as the function suffix; the
            # outer `(int)` is still in the token stream.
            if decl_info.is_paren_wrapped and self._at(TokenType.LPAREN):
                self.advance()  # consume '('
                depth = 1
                while self.current_token and depth > 0:
                    if self._at(TokenType.LPAREN):
                        depth += 1
                    elif self._at(TokenType.RPAREN):
                        depth -= 1
                        if depth == 0:
                            break
                    self.advance()
                self._expect(TokenType.RPAREN, "Expected ')' after return type parameter list")
                ty = Type(base=f"{ty.base} (*)()", is_pointer=True,
                          pointer_level=max(1, int(getattr(ty, "pointer_level", 0) or 1)),
                          line=ty.line, column=ty.column)
                ty._normalize_pointer_state()
                try:
                    ty.fn_param_count = len([p for p in params if getattr(p, "name", None) != "..."])
                    ty.fn_param_types = [p.type for p in params if getattr(p, "name", None) != "..."]
                except Exception:
                    pass

            # Prototype or definition
            if self._match(TokenType.SEMICOLON):
                return FunctionDecl(
                    name=name_tok.value,
                    return_type=ty,
                    parameters=params,
                    body=None,
                    storage_class=storage_class,
                    line=name_tok.line,
                    column=name_tok.column,
                )
            body = self._parse_compound_statement()
            return FunctionDecl(
                name=name_tok.value,
                return_type=ty,
                parameters=params,
                body=body,
                storage_class=storage_class,
                line=name_tok.line,
                column=name_tok.column,
            )

        # --- Variable declaration path ---

        # For function pointer variables like `int (*fp)(int)` and function
        # pointer arrays like `void (*table[])(int)`, _parse_declarator
        # consumed the trailing `(params)` as a function suffix and set
        # is_function=True.  We need to build the function pointer type.
        if decl_info.is_function and not _is_real_function:
            fn_params = decl_info.fn_params
            fn_arity = None
            if fn_params is not None:
                fn_arity = len([p for p in fn_params if getattr(p, "name", None) != "..."])
            # Build function pointer type
            if not ty.is_pointer:
                ty = Type(base=ty.base, is_pointer=True, pointer_level=1,
                          line=ty.line, column=ty.column)
                ty._normalize_pointer_state()
            ty = Type(base=f"{ty.base} (*)()", is_pointer=True,
                      pointer_level=max(1, int(getattr(ty, "pointer_level", 0) or 1)),
                      line=ty.line, column=ty.column)
            ty._normalize_pointer_state()
            try:
                ty.fn_param_count = fn_arity
                ty.fn_return_type = Type(
                    base=base_type.base,
                    is_unsigned=getattr(base_type, 'is_unsigned', False),
                    is_signed=getattr(base_type, 'is_signed', False),
                    line=base_type.line, column=base_type.column)
                if fn_params is not None:
                    ty.fn_param_types = [p.type for p in fn_params
                                         if getattr(p, "name", None) != "..."]
            except Exception:
                pass

        # If we still have a trailing `(params)` for a non-function declarator
        # that was paren-wrapped, handle it here.
        elif self._at(TokenType.LPAREN) and decl_info.is_paren_wrapped and not decl_info.is_function:
            # Trailing parameter list describes the pointed-to function's
            # signature.  Consume it and build function pointer type.
            self.advance()  # consume '('
            try:
                fp_params = self._parse_parameter_list()
                fp_arity = len([p for p in fp_params if getattr(p, "name", None) != "..."])
            except Exception:
                fp_params = None
                fp_arity = None
                depth = 1
                while self.current_token and depth > 0:
                    if self._at(TokenType.LPAREN):
                        depth += 1
                    elif self._at(TokenType.RPAREN):
                        depth -= 1
                        if depth == 0:
                            break
                    self.advance()
            self._expect(TokenType.RPAREN, "Expected ')' after parameter list")
            ty = Type(base=f"{ty.base} (*)()", is_pointer=True,
                      line=ty.line, column=ty.column)
            ty._normalize_pointer_state()

        # --- Build Declaration from DeclaratorInfo ---
        paren_decl = decl_info.is_paren_wrapped
        array_dims = decl_info.array_dims
        array_size_val = None
        if array_dims:
            if not paren_decl:
                array_size_val = array_dims[0]

        # Parse initializer
        initializer = None
        if self._match(TokenType.ASSIGN):
            if self._at(TokenType.LBRACE):
                initializer = self._parse_initializer()
            else:
                initializer = self._parse_assignment()

        decl = Declaration(
            name=name_tok.value,
            type=ty,
            initializer=initializer,
            line=name_tok.line,
            column=name_tok.column,
            array_size=array_size_val,
            array_dims=array_dims if array_dims else None,
        )
        decl.storage_class = storage_class

        # Multi-declarator support for globals: `int a, b, c;`
        if not self._at(TokenType.COMMA):
            self._expect(TokenType.SEMICOLON, "Expected ';' after declaration")
            return decl

        decls = [decl]
        while self._match(TokenType.COMMA):
            extra_info = self._parse_declarator()
            extra_ty = self._apply_declarator(
                Type(
                    base=base_type.base,
                    is_const=base_type.is_const,
                    is_volatile=base_type.is_volatile,
                    is_unsigned=base_type.is_unsigned,
                    is_signed=base_type.is_signed,
                    line=base_type.line,
                    column=base_type.column,
                ),
                extra_info,
            )
            # Handle function pointer suffix for extra declarators
            extra_array_dims = extra_info.array_dims
            extra_array_size = extra_array_dims[0] if extra_array_dims else None
            # Parse initializer for extra declarator
            extra_init = None
            if self._match(TokenType.ASSIGN):
                if self._at(TokenType.LBRACE):
                    extra_init = self._parse_initializer()
                else:
                    extra_init = self._parse_assignment()
            d = Declaration(
                name=extra_info.name,
                type=extra_ty,
                initializer=extra_init,
                line=extra_info.name_tok.line if extra_info.name_tok else base_type.line,
                column=extra_info.name_tok.column if extra_info.name_tok else base_type.column,
                array_size=extra_array_size,
                array_dims=extra_array_dims if extra_array_dims else None,
            )
            d.storage_class = storage_class
            decls.append(d)
        self._expect(TokenType.SEMICOLON, "Expected ';' after declaration")
        return decls

    def _parse_knr_function(self, name_tok: Token, base_type: Type,
                            storage_class: Optional[str]) -> FunctionDecl:
        """Parse a K&R (old-style) function definition.

        Called after the function name and '(' have been consumed, with the
        current token positioned at the first identifier in the parameter
        name list.

        K&R form:  int f(a, b) int a; char *b; { ... }
        """
        knr_names: List[Token] = []
        knr_names.append(self._expect(TokenType.IDENTIFIER, "Expected parameter name"))
        while self._match(TokenType.COMMA):
            knr_names.append(self._expect(TokenType.IDENTIFIER, "Expected parameter name"))
        self._expect(TokenType.RPAREN, "Expected ')' after parameter name list")

        # Parse the K&R parameter declarations (a sequence of declarations
        # ending right before the function body '{').
        param_decl_map: dict = {}
        seen_param_decl: set = set()
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
                    p_base = Type(base=getattr(p_base, "base", "int"),
                                  pointer_level=1, is_pointer=True,
                                  line=getattr(p_base, "line", 1),
                                  column=getattr(p_base, "column", 1))
            p_name_tok = self._expect(TokenType.IDENTIFIER, "Expected identifier")
            self._expect(TokenType.SEMICOLON, "Expected ';' after parameter declaration")
            if p_name_tok.value not in seen_param_decl:
                seen_param_decl.add(p_name_tok.value)
            param_decl_map[p_name_tok.value] = p_base

        # Support optional semicolon between old-style header and the body.
        if self._at(TokenType.SEMICOLON):
            self.advance()

        # Build parameter list in order.  Undeclared params default to int.
        params: List[Declaration] = []
        for nt in knr_names:
            p_ty = param_decl_map.get(nt.value)
            if p_ty is None:
                p_ty = Type(base="int", line=nt.line, column=nt.column)
            params.append(Declaration(name=nt.value, type=p_ty,
                                      line=nt.line, column=nt.column))

        # Extra parameter declarations not in name list => parse-time error.
        extra = [n for n in param_decl_map if n not in {t.value for t in knr_names}]
        if extra:
            raise ParserError(
                "K&R parameter declaration has no matching parameter name",
                self.current_token)

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

    def _parse_struct_or_union_specifier(self) -> Type:
        """Parse struct/union specifier including optional member list.

        Handles: struct Tag, struct Tag { members }, struct { members }
        Returns Type with base="struct Tag" or "union Tag".
        Attaches _inline_members/_anon_members for inline definitions.
        Records members in self._tag_members.

        The caller is responsible for applying qualifiers (const/volatile).
        """
        cur = self.current_token
        kind = cur.value  # 'struct' or 'union'
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

                # C11 anonymous struct/union members: `union { ... };` with
                # no member name.  Skip them gracefully (treat as padding).
                if self._at(TokenType.SEMICOLON):
                    base = getattr(mem_ty, "base", "")
                    if isinstance(base, str) and (base.startswith("struct ") or base.startswith("union ")):
                        self.advance()  # consume ';'
                        continue

                # Anonymous bit-field: `int :32;` — padding, no member name.
                if self._at(TokenType.COLON):
                    self.advance()  # consume ':'
                    bw_expr = self._parse_expression()
                    self._expect(TokenType.SEMICOLON, "Expected ';' after anonymous bit-field")
                    continue

                # --- Unified declarator parsing for struct members ---
                decl_info = self._parse_declarator()
                mem_ty_applied = self._apply_declarator(mem_ty, decl_info)

                # Function pointer member: _parse_declarator sets is_function
                # for patterns like (*name)(params) and (*(*name)(inner))(outer).
                if decl_info.is_function or decl_info.is_paren_wrapped:
                    # For nested function pointers like (*(*xDlSym)(inner))(outer),
                    # _parse_declarator consumes the inner params and sets
                    # is_function=True, but the outer (outer) suffix remains
                    # unconsumed because _parse_declarator_suffixes skips a
                    # second function suffix.  Consume it here.
                    # Also handles simple paren-wrapped declarators like (*fp)
                    # where the trailing (params) wasn't consumed as a suffix.
                    if self._at(TokenType.LPAREN):
                        self.advance()  # consume '('
                        try:
                            self._parse_parameter_list()
                        except Exception:
                            depth = 1
                            while self.current_token and depth > 0:
                                if self._at(TokenType.LPAREN):
                                    depth += 1
                                elif self._at(TokenType.RPAREN):
                                    depth -= 1
                                    if depth == 0:
                                        break
                                self.advance()
                        self._expect(TokenType.RPAREN, "Expected ')' after parameter list")
                    fp_ty = Type(base=f"{mem_ty.base} (*)()", is_pointer=True,
                                 line=mem_ty.line, column=mem_ty.column)
                    fp_ty._normalize_pointer_state()
                    self._expect(TokenType.SEMICOLON, "Expected ';' after member declaration")
                    members.append(Declaration(name=decl_info.name, type=fp_ty,
                                               line=decl_info.name_tok.line if decl_info.name_tok else mem_ty.line,
                                               column=decl_info.name_tok.column if decl_info.name_tok else mem_ty.column))
                    continue

                # Bit-field: member_name : width
                bit_width = None
                if self._match(TokenType.COLON):
                    bw_expr = self._parse_expression()
                    if isinstance(bw_expr, IntLiteral):
                        bit_width = int(bw_expr.value)
                    else:
                        bit_width = 0

                array_dims = decl_info.array_dims
                d = Declaration(
                    name=decl_info.name,
                    type=mem_ty_applied,
                    line=decl_info.name_tok.line if decl_info.name_tok else mem_ty.line,
                    column=decl_info.name_tok.column if decl_info.name_tok else mem_ty.column,
                )
                if array_dims:
                    d.array_size = array_dims[0]
                    d.array_dims = array_dims
                if bit_width is not None:
                    d.bit_width = bit_width
                members.append(d)

                # Multi-declarator: int a, b, *c;
                while self._match(TokenType.COMMA):
                    extra_info = self._parse_declarator()
                    extra_ty = self._apply_declarator(
                        Type(
                            base=mem_ty.base,
                            is_const=mem_ty.is_const,
                            is_volatile=mem_ty.is_volatile,
                            is_unsigned=mem_ty.is_unsigned,
                            is_signed=mem_ty.is_signed,
                            line=mem_ty.line,
                            column=mem_ty.column,
                        ),
                        extra_info,
                    )
                    extra_array_dims = extra_info.array_dims
                    ebw = None
                    if self._match(TokenType.COLON):
                        bw_expr = self._parse_expression()
                        ebw = int(bw_expr.value) if isinstance(bw_expr, IntLiteral) else 0
                    ed = Declaration(
                        name=extra_info.name,
                        type=extra_ty,
                        line=extra_info.name_tok.line if extra_info.name_tok else mem_ty.line,
                        column=extra_info.name_tok.column if extra_info.name_tok else mem_ty.column,
                    )
                    if extra_array_dims:
                        ed.array_size = extra_array_dims[0]
                        ed.array_dims = extra_array_dims
                    if ebw is not None:
                        ed.bit_width = ebw
                    members.append(ed)

                self._expect(TokenType.SEMICOLON, "Expected ';' after member declaration")
            self._expect(TokenType.RBRACE, "Expected '}' after struct/union members")

            # Remember members for named tags so outer declaration `struct T {...};`
            # can be materialized as a StructDecl/UnionDecl node.
            if tag_tok is not None:
                self._tag_members[f"{kind} {tag_tok.value}"] = members

        # Generate a unique synthetic tag for anonymous struct/union definitions.
        # This gives nested anonymous types a stable identity so downstream
        # passes (semantics layout, blob packer, sizeof, codegen) can look them
        # up by type name.  Without this, every anonymous nested struct/union
        # would collide on the string "struct <anonymous>" / "union <anonymous>".
        if tag_tok is None and members is not None:
            self._anon_tag_counter += 1
            synth_tag = f"__anon_{kind}_{self._anon_tag_counter}"
            self._tag_members[f"{kind} {synth_tag}"] = members
            base_ty = Type(base=f"{kind} {synth_tag}", line=cur.line, column=cur.column)
            base_ty._anon_members = members
            return base_ty

        # record a textual type name for now: e.g. "struct Point"
        tag_name = tag_tok.value if tag_tok else "<anonymous>"
        base_ty = Type(base=f"{kind} {tag_name}", line=cur.line, column=cur.column)
        # Attach members to the Type node so that semantics can register
        # the layout even when no standalone StructDecl node is emitted
        # (e.g. `static struct S { int x; } var;`).
        if members is not None:
            if tag_tok is None:
                base_ty._anon_members = members
            else:
                base_ty._inline_members = members
        return base_ty

    def _parse_enum_specifier(self) -> Type:
        """Parse enum specifier including optional enumerator list.

        Handles: enum Tag, enum Tag { enumerators }, enum { enumerators }
        Returns Type with base="enum Tag".
        Queues EnumDecl in self._pending_enum_decls.

        The caller is responsible for applying qualifiers (const/volatile).
        """
        cur = self.current_token
        self.advance()  # consume 'enum'
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
                    line=cur.line,
                    column=cur.column,
                )
            )

        tag_name = tag_tok.value if tag_tok else "<anonymous>"
        t = Type(base=f"enum {tag_name}", line=cur.line, column=cur.column)
        return t

    # ------------------------------------------------------------------
    # _build_type_from_specifiers: construct a Type from collected
    # declaration-specifier state.  This is a pure normalization step
    # that does NOT consume tokens — it only interprets the accumulated
    # qualifier / sign / size / base / tag / typedef information.
    # ------------------------------------------------------------------
    def _build_type_from_specifiers(
        self,
        quals: set,
        sign: Optional[str],
        size: Optional[str],
        base: Optional[str],
        tag_type: Optional[Type],
        typedef_name: Optional[str],
        start_tok: Optional[Token],
    ) -> Type:
        """Construct a Type from collected declaration specifiers.

        Normalization rules (C89 §6.5.2):
        - unsigned/signed + int/char/short/long combinations
        - bare unsigned -> unsigned int, bare long -> long int, etc.
        - long double
        - tag_type passthrough with quals applied
        - typedef_name passthrough with quals applied
        - implicit int from bare sign/size specifiers
        - nothing set -> error
        """
        line = start_tok.line if start_tok else 0
        col = start_tok.column if start_tok else 0
        is_const = "const" in quals
        is_volatile = "volatile" in quals

        # --- tag_type passthrough (struct/union/enum) ---
        if tag_type is not None:
            tag_type.is_const = is_const
            tag_type.is_volatile = is_volatile
            return tag_type

        # --- typedef_name passthrough ---
        if typedef_name is not None:
            t = Type(base=typedef_name, line=line, column=col)
            t.is_const = is_const
            t.is_volatile = is_volatile
            return t

        # --- explicit base type keyword present ---
        if base is not None:
            t = Type(base=base, line=line, column=col)
            t.is_const = is_const
            t.is_volatile = is_volatile
            t.is_unsigned = (sign == "unsigned")
            t.is_signed = (sign == "signed")

            # size + base combinations
            if base == "int" and size in {"short", "long", "long long"}:
                t.base = f"{size} int"
            if base == "double" and size == "long":
                t.base = "long double"

            # Normalize unsigned/signed into base string for downstream
            # string-based checks used throughout the compiler.
            if t.base == "int":
                if sign == "unsigned":
                    t.base = "unsigned int"
                # signed int is just "int"
            elif t.base == "char":
                if sign == "unsigned":
                    t.base = "unsigned char"
                # signed char is just "char"
            elif t.base == "short int":
                if sign == "unsigned":
                    t.base = "unsigned short"
            elif t.base == "long int":
                if sign == "unsigned":
                    t.base = "unsigned long"
            elif t.base == "long long int":
                if sign == "unsigned":
                    t.base = "unsigned long long"

            return t

        # --- no explicit base: implicit int from sign/size specifiers ---
        if sign is not None or size is not None:
            t = Type(base="int", line=line, column=col)
            t.is_const = is_const
            t.is_volatile = is_volatile
            t.is_unsigned = (sign == "unsigned")
            t.is_signed = (sign == "signed")

            if size in {"short", "long", "long long"}:
                t.base = f"{size} int"

            # Normalize unsigned into base string
            if t.base == "int" and sign == "unsigned":
                t.base = "unsigned int"
            elif t.base == "short int" and sign == "unsigned":
                t.base = "unsigned short"
            elif t.base == "long int" and sign == "unsigned":
                t.base = "unsigned long"
            elif t.base == "long long int" and sign == "unsigned":
                t.base = "unsigned long long"

            return t

        # --- bare qualifiers with no type at all -> error ---
        raise ParserError("Expected type specifier", start_tok)

    def _parse_type_specifier(self) -> Type:
        """Parse a C declaration-specifier sequence and return a Type.

        Single-loop collector: accumulates qualifiers, sign, size, base type,
        struct/union/enum tag, or typedef name, then delegates to
        _build_type_from_specifiers for normalization.

        C allows qualifiers both before and after the base type:
          const int   ←→   int const
          volatile char  ←→  char volatile
        Trailing qualifiers are absorbed after the base type terminates the
        main loop, so callers always see a clean token stream.

        Extension point: to add a new type keyword (e.g. _Bool, long long),
        add an elif branch in the collection loop below.
        """
        start_tok = self.current_token
        if not self._is_type_specifier():
            raise ParserError("Expected type specifier", start_tok)

        quals: set = set()           # {'const', 'volatile'}
        sign: Optional[str] = None   # 'signed' | 'unsigned'
        size: Optional[str] = None   # 'short' | 'long'
        base: Optional[str] = None   # 'int' | 'char' | 'void' | ...
        tag_type: Optional[Type] = None    # from struct/union/enum
        typedef_name: Optional[str] = None # typedef identifier

        while self.current_token:
            tok = self.current_token
            # Qualifiers and modifiers are keywords
            if tok.type == TokenType.KEYWORD:
                v = tok.value
                if v in {"const", "volatile"}:
                    quals.add(v)
                    self.advance()
                    continue
                if v in {"unsigned", "signed"}:
                    sign = v
                    self.advance()
                    continue
                if v in {"short", "long"}:
                    # Accumulate 'long long' when two consecutive 'long' appear.
                    if v == "long" and size == "long":
                        size = "long long"
                    else:
                        size = v
                    self.advance()
                    continue
                # --- Base type keywords ---
                # To add a new base type (e.g. _Bool, _Complex), add it here.
                # For multi-word sizes (e.g. long long), extend the 'size'
                # handling above to accumulate a list instead of a single str.
                if v in {"int", "char", "void", "float", "double",
                         "__builtin_va_list"}:
                    base = v
                    self.advance()
                    break  # base type keyword terminates collection
                if v in {"struct", "union"}:
                    tag_type = self._parse_struct_or_union_specifier()
                    break
                if v == "enum":
                    tag_type = self._parse_enum_specifier()
                    break
            # Typedef name (identifier in _typedefs set)
            if (tok.type == TokenType.IDENTIFIER
                    and tok.value in self._typedefs):
                typedef_name = tok.value
                self.advance()
                break
            # Unrecognized token — stop collecting
            break

        # Absorb trailing qualifiers: `int const`, `struct Foo volatile`, etc.
        # C89 §6.5.2 allows qualifiers in any order relative to the base type.
        while (self.current_token
               and self.current_token.type == TokenType.KEYWORD
               and self.current_token.value in {"const", "volatile"}):
            quals.add(self.current_token.value)
            self.advance()

        return self._build_type_from_specifiers(
            quals, sign, size, base, tag_type, typedef_name, start_tok)

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
            # varargs: `...` appears after a comma in prototypes.
            if self.current_token and self.current_token.type == TokenType.ELLIPSIS:
                self.advance()
                params.append(Declaration(name="...", type=Type(base="int", line=0, column=0), line=0, column=0))
                break

            base_type = self._parse_type_specifier()

            # --- Unified declarator parsing (allow unnamed / abstract) ---
            decl_info = self._parse_declarator(allow_abstract=True)
            param_ty = self._apply_declarator(base_type, decl_info)

            # --- Function pointer parameter ---
            if decl_info.is_function:
                fn_params = decl_info.fn_params
                fn_arity = None
                if fn_params is not None:
                    fn_arity = len([p for p in fn_params if getattr(p, "name", None) != "..."])
                # Build function pointer type for downstream compatibility.
                ptr_ty = param_ty
                if not ptr_ty.is_pointer:
                    ptr_ty = Type(base=ptr_ty.base, is_pointer=True, pointer_level=1,
                                  line=ptr_ty.line, column=ptr_ty.column)
                    ptr_ty._normalize_pointer_state()
                ptr_ty = Type(base=f"{ptr_ty.base} (*)()", is_pointer=True,
                              pointer_level=max(1, int(getattr(ptr_ty, "pointer_level", 0) or 1)),
                              line=ptr_ty.line, column=ptr_ty.column)
                ptr_ty._normalize_pointer_state()
                try:
                    ptr_ty.fn_param_count = fn_arity
                    ptr_ty.fn_return_type = Type(
                        base=base_type.base,
                        is_unsigned=getattr(base_type, 'is_unsigned', False),
                        is_signed=getattr(base_type, 'is_signed', False),
                        line=base_type.line, column=base_type.column)
                    if fn_params is not None:
                        ptr_ty.fn_param_types = [p.type for p in fn_params
                                                 if getattr(p, "name", None) != "..."]
                except Exception:
                    pass
                name = decl_info.name
                line = decl_info.name_tok.line if decl_info.name_tok else ptr_ty.line
                col = decl_info.name_tok.column if decl_info.name_tok else ptr_ty.column
                params.append(Declaration(name=name, type=ptr_ty, line=line, column=col))

            # --- Array parameter: C89 §6.7.1 array-to-pointer adjustment ---
            elif decl_info.array_dims:
                param_ty = Type(base=param_ty.base, is_pointer=True,
                                pointer_level=int(getattr(param_ty, 'pointer_level', 0) or 0) + 1,
                                is_unsigned=getattr(param_ty, 'is_unsigned', False),
                                is_signed=getattr(param_ty, 'is_signed', False),
                                line=param_ty.line, column=param_ty.column)
                param_ty._normalize_pointer_state()
                name = decl_info.name
                line = decl_info.name_tok.line if decl_info.name_tok else param_ty.line
                col = decl_info.name_tok.column if decl_info.name_tok else param_ty.column
                params.append(Declaration(name=name, type=param_ty, line=line, column=col))

            # --- Normal parameter (named or unnamed) ---
            else:
                name = decl_info.name
                line = decl_info.name_tok.line if decl_info.name_tok else param_ty.line
                col = decl_info.name_tok.column if decl_info.name_tok else param_ty.column
                params.append(Declaration(name=name, type=param_ty, line=line, column=col))

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

    def _skip_pointer_qualifiers(self) -> None:
        """Consume pointer-level qualifiers (const, volatile, restrict) after '*'.

        In C89, `int * const p` declares p as a const pointer to int.
        These qualifiers appear between '*' and the declarator name.
        """
        _QUALS = {"const", "volatile", "restrict", "__restrict", "__restrict__"}
        while (self.current_token
               and self.current_token.type == TokenType.KEYWORD
               and self.current_token.value in _QUALS):
            self.advance()

    # Statements

    def _parse_compound_statement(self) -> CompoundStmt:
        lbrace = self._expect(TokenType.LBRACE, "Expected '{'")
        items: List[Union[Declaration, object]] = []
        while not self._at(TokenType.RBRACE):
            if self._at(TokenType.EOF):
                raise ParserError("Unterminated compound statement", self.current_token)
            if self._is_type_specifier():
                decls = self._parse_local_declaration()
                if isinstance(decls, list):
                    items.extend(decls)
                else:
                    items.append(decls)
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

        # --- Local typedef ---
        if self.current_token and self.current_token.type == TokenType.KEYWORD and self.current_token.value == "typedef":
            self.advance()
            base_type = self._parse_type_specifier()
            decl_info = self._parse_declarator()
            td = self._build_typedef_decl(base_type, decl_info)
            self._typedefs.add(td.name)
            self._typedef_types[td.name] = td.type
            # Multi-name local typedef: typedef struct _S *A, *B;
            while self._match(TokenType.COMMA):
                extra_info = self._parse_declarator()
                etd = self._build_typedef_decl(base_type, extra_info)
                self._typedefs.add(etd.name)
                self._typedef_types[etd.name] = etd.type
            self._expect(TokenType.SEMICOLON, "Expected ';' after typedef")
            return td

        base_type = self._parse_type_specifier()

        # Standalone struct/union/enum definition: `struct S { ... };`
        if self._at(TokenType.SEMICOLON):
            b = getattr(base_type, "base", "")
            if isinstance(b, str) and (b.startswith("struct ") or b.startswith("union ") or b.startswith("enum ")):
                self.advance()  # consume ';'
                return Declaration(name="__tagdecl__", type=base_type,
                                   line=base_type.line, column=base_type.column)

        # --- Unified declarator parsing ---
        decl_info = self._parse_declarator()
        name_tok = decl_info.name_tok
        ty = self._apply_declarator(base_type, decl_info)

        # --- Handle function pointer variables ---
        # _parse_declarator may have consumed a trailing (params) suffix and
        # set is_function=True.  For local declarations this always means a
        # function pointer variable (not a real function definition).
        if decl_info.is_function:
            fn_params = decl_info.fn_params
            fn_arity = None
            if fn_params is not None:
                fn_arity = len([p for p in fn_params if getattr(p, "name", None) != "..."])
            if not ty.is_pointer:
                ty = Type(base=ty.base, is_pointer=True, pointer_level=1,
                          line=ty.line, column=ty.column)
                ty._normalize_pointer_state()
            ty = Type(base=f"{ty.base} (*)()", is_pointer=True,
                      pointer_level=max(1, int(getattr(ty, "pointer_level", 0) or 1)),
                      line=ty.line, column=ty.column)
            ty._normalize_pointer_state()
            try:
                ty.fn_param_count = fn_arity
                ty.fn_return_type = Type(
                    base=base_type.base,
                    is_unsigned=getattr(base_type, 'is_unsigned', False),
                    is_signed=getattr(base_type, 'is_signed', False),
                    line=base_type.line, column=base_type.column)
                if fn_params is not None:
                    ty.fn_param_types = [p.type for p in fn_params
                                         if getattr(p, "name", None) != "..."]
            except Exception:
                pass
        elif self._at(TokenType.LPAREN) and decl_info.is_paren_wrapped and not decl_info.is_function:
            # Trailing parameter list for paren-wrapped pointer declarator
            # e.g. void (*fp)(int) where _parse_declarator only consumed (*fp)
            self.advance()  # consume '('
            try:
                fp_params = self._parse_parameter_list()
                fp_arity = len([p for p in fp_params if getattr(p, "name", None) != "..."])
            except Exception:
                fp_params = None
                fp_arity = None
                depth = 1
                while self.current_token and depth > 0:
                    if self._at(TokenType.LPAREN):
                        depth += 1
                    elif self._at(TokenType.RPAREN):
                        depth -= 1
                        if depth == 0:
                            break
                    self.advance()
            self._expect(TokenType.RPAREN, "Expected ')' after parameter list")
            ty = Type(base=f"{ty.base} (*)()", is_pointer=True,
                      line=ty.line, column=ty.column)
            ty._normalize_pointer_state()

        # --- Build Declaration from DeclaratorInfo ---
        paren_decl = decl_info.is_paren_wrapped
        array_dims = decl_info.array_dims
        array_size_val = None
        if array_dims:
            # For parenthesized declarators like int (*p)[N], the [N] describes
            # the pointed-to array, not this variable's array dimension.
            # But for array-of-function-pointers like int (*fp[2])(int), the
            # [2] IS the variable's array dimension (inside the parens, before
            # the function suffix).  When is_function is set, the array dims
            # belong to the variable.
            if not paren_decl or decl_info.is_function:
                array_size_val = array_dims[0]

        # Parse initializer
        initializer = None
        if self._match(TokenType.ASSIGN):
            if self._at(TokenType.LBRACE):
                initializer = self._parse_initializer()
            else:
                initializer = self._parse_assignment()

        decl = Declaration(
            name=name_tok.value,
            type=ty,
            initializer=initializer,
            line=name_tok.line,
            column=name_tok.column,
            array_size=array_size_val,
            array_dims=array_dims if array_dims else None,
        )
        decl.storage_class = storage_class

        # --- Multi-declarator: int a, b, c; ---
        if not self._at(TokenType.COMMA):
            self._expect(TokenType.SEMICOLON, "Expected ';' after declaration")
            return decl

        decls = [decl]
        while self._match(TokenType.COMMA):
            extra_info = self._parse_declarator()
            extra_ty = self._apply_declarator(
                Type(
                    base=base_type.base,
                    is_const=base_type.is_const,
                    is_volatile=base_type.is_volatile,
                    is_unsigned=base_type.is_unsigned,
                    is_signed=base_type.is_signed,
                    line=base_type.line,
                    column=base_type.column,
                ),
                extra_info,
            )
            extra_array_dims = extra_info.array_dims
            extra_array_size = extra_array_dims[0] if extra_array_dims else None
            # Parse initializer for extra declarator
            extra_init = None
            if self._match(TokenType.ASSIGN):
                if self._at(TokenType.LBRACE):
                    extra_init = self._parse_initializer()
                else:
                    extra_init = self._parse_assignment()
            d = Declaration(
                name=extra_info.name,
                type=extra_ty,
                initializer=extra_init,
                line=extra_info.name_tok.line if extra_info.name_tok else base_type.line,
                column=extra_info.name_tok.column if extra_info.name_tok else base_type.column,
                array_size=extra_array_size,
                array_dims=extra_array_dims if extra_array_dims else None,
            )
            d.storage_class = storage_class
            decls.append(d)
        self._expect(TokenType.SEMICOLON, "Expected ';' after declaration")
        return decls

    # ------------------------------------------------------------------ #
    #  Unified declarator parser (C89 §6.5.4 / C99 §6.7.5)              #
    # ------------------------------------------------------------------ #

    def _parse_declarator(self, allow_abstract: bool = False) -> DeclaratorInfo:
        """Parse a C declarator (recursive).

        Grammar:
            declarator          = pointer? direct-declarator
            pointer             = '*' type-qualifier-list? pointer?
            direct-declarator   = identifier
                                | '(' declarator ')'
                                | direct-declarator '[' constant-expr? ']'
                                | direct-declarator '(' parameter-list ')'

        Args:
            allow_abstract: If True, the name is optional (for casts, sizeof).

        Returns:
            DeclaratorInfo with all parsed information.
        """
        info = DeclaratorInfo()

        # --- 1. Pointer prefix: consume '*' and per-level qualifiers ---
        # Stars are parsed left-to-right (innermost first, outermost last).
        # The Type convention is outermost-first (index 0 = closest to name),
        # so we reverse after collecting all levels.
        _QUALS = {"const", "volatile", "restrict", "__restrict", "__restrict__"}
        while self._match(TokenType.STAR):
            info.pointer_level += 1
            quals: Set[str] = set()
            while (self.current_token
                   and self.current_token.type == TokenType.KEYWORD
                   and self.current_token.value in _QUALS):
                q = self.current_token.value
                if q in ("__restrict", "__restrict__"):
                    q = "restrict"
                quals.add(q)
                self.advance()
            info.pointer_quals.append(quals)
        # Reverse so index 0 = outermost pointer level (closest to name).
        info.pointer_quals.reverse()

        # --- 2. Direct declarator ---
        if self._at(TokenType.LPAREN):
            # Disambiguate: '(' declarator ')' vs '(' parameter-list ')'
            # Heuristic: if the token after '(' is '*' or '(' it is a
            # parenthesized declarator.  If it is an identifier we need to
            # peek further: identifier followed by ')' or ',' means it is
            # just a parenthesized name (like Lua's `int (func)(params)`),
            # while identifier followed by a type-start means parameter list.
            if self._is_paren_declarator_start():
                self.advance()  # consume '('
                inner = self._parse_declarator(allow_abstract=allow_abstract)
                self._expect(TokenType.RPAREN, "Expected ')' after parenthesized declarator")
                # Merge: outer pointers wrap around inner declarator.
                # The C declaration reading rule says inner binds first, then
                # outer pointers are applied.  We record the paren-wrapped flag
                # so callers can distinguish `int (x)` from `int x`.
                inner.is_paren_wrapped = True
                # Prepend outer pointer levels: outer pointers are "more indirect"
                # than inner ones.  In `int *(*p)`, outer `*` is level 2, inner
                # `*` is level 1.  pointer_quals list is outermost-first.
                if info.pointer_level > 0:
                    inner.outer_pointer_level = info.pointer_level
                    inner.pointer_quals = info.pointer_quals + inner.pointer_quals
                    inner.pointer_level += info.pointer_level
                info = inner
            elif allow_abstract:
                # Abstract declarator with no name — the '(' we see is NOT
                # consumed; it belongs to the caller (e.g. a cast expression
                # or sizeof).  Return what we have so far.
                pass
            else:
                raise ParserError(
                    "Expected identifier or '(' in declarator",
                    self.current_token,
                )
        elif self._at(TokenType.IDENTIFIER):
            info.name_tok = self.current_token
            info.name = self.current_token.value
            self.advance()
        else:
            if not allow_abstract:
                raise ParserError(
                    "Expected identifier in declarator",
                    self.current_token,
                )
            # Abstract declarator — no name, just pointer/array/function suffixes.

        # --- 3. Suffixes: array dimensions and function parameter lists ---
        self._parse_declarator_suffixes(info)

        return info

    def _is_paren_declarator_start(self) -> bool:
        """Decide whether the current '(' begins a parenthesized declarator.

        Called when current token is '('.  Returns True if the contents look
        like a nested declarator rather than a parameter list.

        Heuristics (in order):
        1. '(' '*'  → pointer declarator like (*fp)
        2. '(' '('  → nested parens like ((*fp))
        3. '(' IDENT ')'  → parenthesized name like (func)
        4. '(' IDENT '[' → parenthesized array like (arr[10])
        5. Otherwise → assume parameter list
        """
        nxt = self.peek(1)
        if nxt is None:
            return False
        # Case 1: '(' '*' — pointer declarator
        if nxt.type == TokenType.STAR:
            return True
        # Case 2: '(' '(' — nested parens
        if nxt.type == TokenType.LPAREN:
            return True
        # Case 3/4: '(' IDENT ...
        if nxt.type == TokenType.IDENTIFIER:
            nxt2 = self.peek(2)
            if nxt2 is None:
                return False
            # '(' name ')' — parenthesized name
            if nxt2.type == TokenType.RPAREN:
                return True
            # '(' name '[' — parenthesized array declarator
            if nxt2.type == TokenType.LBRACKET:
                return True
            # '(' name '(' — could be function declarator name with params
            # e.g. int (func)(int x) — the name is followed by '(' for params
            # but that '(' is OUTSIDE the parens, so '(' name '(' means
            # the inner '(' closes after name, then outer '(' starts params.
            # Actually in `int (func)(int x)`, tokens are: ( func ) ( int x )
            # So '(' IDENT ')' is already handled above.
            # If we see '(' IDENT COMMA or '(' IDENT KEYWORD, it's a param list.
            return False
        return False

    def _apply_declarator(self, base_type: Type, info: DeclaratorInfo) -> Type:
        """Apply pointer levels from DeclaratorInfo onto a base Type.

        This builds a new Type with the correct pointer_level and
        pointer_quals.  It does NOT handle array_dims or fn_params — those
        are stored on the Declaration node by the caller.

        Args:
            base_type: The type from declaration-specifiers (e.g. `int`,
                       `const struct Foo`).
            info: The parsed declarator information.

        Returns:
            A (possibly new) Type with pointer levels applied.
        """
        if info.pointer_level == 0:
            return base_type

        ty = Type(
            base=base_type.base,
            is_pointer=True,
            pointer_level=info.pointer_level,
            is_const=getattr(base_type, 'is_const', False),
            is_volatile=getattr(base_type, 'is_volatile', False),
            is_restrict=getattr(base_type, 'is_restrict', False),
            is_unsigned=getattr(base_type, 'is_unsigned', False),
            is_signed=getattr(base_type, 'is_signed', False),
            line=base_type.line,
            column=base_type.column,
        )
        # pointer_quals in DeclaratorInfo is outermost-first (closest to name
        # first).  Type.pointer_quals uses the same convention.
        ty.pointer_quals = [set(q) for q in info.pointer_quals]
        ty._normalize_pointer_state()
        return ty

    def _build_typedef_decl(self, base_type: Type, info: DeclaratorInfo) -> 'TypedefDecl':
        """Build a TypedefDecl from a base type and parsed DeclaratorInfo.

        Handles all typedef forms:
          - Simple:          typedef int myint;
          - Pointer:         typedef int *intptr;
          - Function pointer: typedef int (*fp)(int);
          - Function type:   typedef int func_t(int);
          - Array:           typedef int arr_t[23];
          - Multi-dim array: typedef int mat_t[3][4];

        Args:
            base_type: The type from declaration-specifiers.
            info: The parsed declarator information.

        Returns:
            A TypedefDecl node.
        """
        name = info.name
        name_tok = info.name_tok
        line = name_tok.line if name_tok else base_type.line
        col = name_tok.column if name_tok else base_type.column

        # Determine if this is a function pointer or function type typedef.
        if info.is_function:
            # Build function pointer type for downstream compatibility.
            # Both `typedef int (*fp)(int)` and `typedef int func_t(int)`
            # produce a function pointer type `base (*)()`.
            ty = self._apply_declarator(base_type, info)
            fp_ty = Type(base=f"{base_type.base} (*)()", is_pointer=True,
                         line=base_type.line, column=base_type.column)
            fp_ty._normalize_pointer_state()
            td = TypedefDecl(name=name, type=fp_ty, line=line, column=col)
            return td

        # Apply pointer levels from declarator to base type.
        ty = self._apply_declarator(base_type, info)

        td = TypedefDecl(name=name, type=ty, line=line, column=col)

        # Record array dimensions if present.
        if info.array_dims:
            td.array_size = info.array_dims[0]
            td.array_dims = list(info.array_dims)

        return td

    def _try_eval_const_expr(self, expr) -> Optional[int]:
        """Best-effort compile-time integer constant expression evaluator.

        Used by the parser to evaluate array dimension expressions like
        `sizeof(void*) + sizeof(long)`. Returns None if the expression
        cannot be evaluated at parse time.
        """
        if isinstance(expr, IntLiteral):
            return int(expr.value)
        if isinstance(expr, CharLiteral):
            return ord(expr.value)
        if isinstance(expr, SizeOf):
            return self._try_eval_sizeof(expr)
        if isinstance(expr, UnaryOp):
            v = self._try_eval_const_expr(expr.operand)
            if v is None:
                return None
            if expr.operator == '+': return v
            if expr.operator == '-': return -v
            if expr.operator == '~': return ~v
            if expr.operator == '!': return 0 if v != 0 else 1
            return None
        if isinstance(expr, BinaryOp):
            l = self._try_eval_const_expr(expr.left)
            r = self._try_eval_const_expr(expr.right)
            if l is None or r is None:
                return None
            op = expr.operator
            if op == '+': return l + r
            if op == '-': return l - r
            if op == '*': return l * r
            if op == '/': return l // r if r != 0 else None
            if op == '%': return l % r if r != 0 else None
            if op == '|': return l | r
            if op == '&': return l & r
            if op == '^': return l ^ r
            if op == '<<': return l << r
            if op == '>>': return l >> r
            if op == '<': return 1 if l < r else 0
            if op == '>': return 1 if l > r else 0
            if op == '<=': return 1 if l <= r else 0
            if op == '>=': return 1 if l >= r else 0
            if op == '==': return 1 if l == r else 0
            if op == '!=': return 1 if l != r else 0
            return None
        if isinstance(expr, Cast):
            return self._try_eval_const_expr(expr.expression)
        if isinstance(expr, TernaryOp):
            cond = self._try_eval_const_expr(expr.condition)
            if cond is None:
                return None
            if cond != 0:
                return self._try_eval_const_expr(expr.true_expr)
            return self._try_eval_const_expr(expr.false_expr)
        return None

    def _try_eval_sizeof(self, expr) -> Optional[int]:
        """Evaluate sizeof at parse time (best-effort)."""
        # sizeof(type-name)
        if expr.type is not None:
            ty = expr.type
            base = getattr(ty, 'base', None)
            if isinstance(base, str):
                # Primitive types — includes all normalized forms produced by
                # _build_type_from_specifiers (e.g. 'long int', 'short int').
                _SIZES = {
                    'char': 1, 'signed char': 1, 'unsigned char': 1,
                    'short': 2, 'signed short': 2, 'unsigned short': 2,
                    'short int': 2, 'signed short int': 2, 'unsigned short int': 2,
                    'int': 4, 'signed int': 4, 'unsigned int': 4,
                    'long': 8, 'signed long': 8, 'unsigned long': 8,
                    'long int': 8, 'signed long int': 8, 'unsigned long int': 8,
                    'long long': 8, 'signed long long': 8, 'unsigned long long': 8,
                    'long long int': 8, 'signed long long int': 8, 'unsigned long long int': 8,
                    'float': 4, 'double': 8, 'long double': 16,
                    'void': 1,
                }
                if getattr(ty, 'is_pointer', False) or (getattr(ty, 'pointer_level', 0) or 0) > 0:
                    return 8  # LP64 pointer size
                sz = _SIZES.get(base)
                if sz is not None:
                    return sz
                # Resolve typedef names recursively to find underlying type size.
                resolved = self._resolve_typedef_for_sizeof(base)
                if resolved is not None:
                    return resolved
            return None
        # sizeof(expression) — limited support
        op = expr.operand
        if op is not None:
            from pycc.ast_nodes import StringLiteral
            if isinstance(op, StringLiteral):
                return len(op.value) + 1
        return None

    def _resolve_typedef_for_sizeof(self, name: str) -> Optional[int]:
        """Recursively resolve a typedef name to compute its size for sizeof."""
        _SIZES = {
            'char': 1, 'signed char': 1, 'unsigned char': 1,
            'short': 2, 'signed short': 2, 'unsigned short': 2,
            'short int': 2, 'signed short int': 2, 'unsigned short int': 2,
            'int': 4, 'signed int': 4, 'unsigned int': 4,
            'long': 8, 'signed long': 8, 'unsigned long': 8,
            'long int': 8, 'signed long int': 8, 'unsigned long int': 8,
            'long long': 8, 'signed long long': 8, 'unsigned long long': 8,
            'long long int': 8, 'signed long long int': 8, 'unsigned long long int': 8,
            'float': 4, 'double': 8, 'long double': 16,
            'void': 1,
        }
        visited = set()
        current = name
        while current and current not in visited:
            visited.add(current)
            ty = self._typedef_types.get(current)
            if ty is None:
                return None
            # If the resolved type is a pointer, size is 8
            if getattr(ty, 'is_pointer', False) or (getattr(ty, 'pointer_level', 0) or 0) > 0:
                return 8
            base = getattr(ty, 'base', None)
            if not isinstance(base, str):
                return None
            sz = _SIZES.get(base)
            if sz is not None:
                return sz
            # base might be another typedef name — continue resolving
            current = base
        return None

    def _parse_declarator_suffixes(self, info: DeclaratorInfo) -> None:
        """Parse array and function suffixes into an existing DeclaratorInfo.

        This is the shared suffix-parsing loop used by _parse_declarator.
        It consumes:
          - Array suffixes:    [N], [], [N][M]
          - Function suffixes: (parameter-list)

        The results are stored directly into *info*.
        """
        while True:
            if self._match(TokenType.LBRACKET):
                # Array suffix: [N] or []
                dim: Optional[int] = None
                if not self._at(TokenType.RBRACKET):
                    size_expr = self._parse_expression()
                    # Evaluate constant expression for array dimension.
                    # Handles sizeof, arithmetic, casts, etc.
                    dim = self._try_eval_const_expr(size_expr)
                self._expect(TokenType.RBRACKET, "Expected ']' in array declarator")
                info.array_dims.append(dim)
            elif self._at(TokenType.LPAREN) and not info.is_function:
                # Function parameter suffix.
                self.advance()  # consume '('
                info.is_function = True
                try:
                    params = self._parse_parameter_list()
                    info.fn_params = params
                    info.fn_is_variadic = any(
                        getattr(p, "name", None) == "..." for p in params
                    )
                except Exception as _param_err:
                    # Best-effort: skip to matching ')'
                    info.fn_params = None
                    depth = 1
                    while self.current_token and depth > 0:
                        if self._at(TokenType.EOF):
                            # No matching ')' found — re-raise the original error
                            # so the caller gets a meaningful error position.
                            raise _param_err
                        if self._at(TokenType.LPAREN):
                            depth += 1
                        elif self._at(TokenType.RPAREN):
                            depth -= 1
                            if depth == 0:
                                break
                        self.advance()
                # Permissive: if _parse_parameter_list stopped early (e.g.
                # function-type parameters like `int f()`), skip remaining
                # tokens to the matching ')'.
                if not self._at(TokenType.RPAREN):
                    depth = 1
                    while self.current_token and depth > 0:
                        if self._at(TokenType.EOF):
                            break
                        if self._at(TokenType.LPAREN):
                            depth += 1
                        elif self._at(TokenType.RPAREN):
                            depth -= 1
                            if depth == 0:
                                break
                        self.advance()
                self._expect(TokenType.RPAREN, "Expected ')' after parameter list")
            else:
                break

    def _parse_initializer(self) -> Expression:
        """Parse an initializer.

        Supported:
        - assignment-expression
        - initializer-list: '{' [initializer (',' initializer)*] [','] '}'
        - designated initializers: '.member = val', '[index] = val'
        - nested designators: '.inner.member = val'
        - mixed designated and non-designated elements
        """

        # initializer-list
        if self._match(TokenType.LBRACE):
            elements: List[tuple[Optional[object], object]] = []
            # empty initializer list => zero-init
            if not self._at(TokenType.RBRACE):
                while True:
                    designator = self._try_parse_designator()
                    val = self._parse_initializer()
                    elements.append((designator, val))
                    if not self._match(TokenType.COMMA):
                        break
                    if self._at(TokenType.RBRACE):
                        break
            rbrace = self._expect(TokenType.RBRACE, "Expected '}' after initializer")
            return Initializer(elements=elements, line=rbrace.line, column=rbrace.column)

        # assignment-expression
        return self._parse_assignment()

    def _try_parse_designator(self) -> Optional[Designator]:
        """Try to parse a designator prefix before an initializer element.

        Recognizes:
        - .member = val  (member designator)
        - [index] = val  (array designator)
        - .inner.member = val  (nested designators)
        - [i].member = val  (mixed nested designators)

        Returns None if no designator prefix is found.
        """
        if not self._at(TokenType.DOT) and not self._at(TokenType.LBRACKET):
            return None

        # For '.', check that the next token is an identifier followed by
        # either '=' or another designator start ('.' or '[').
        if self._at(TokenType.DOT):
            p1 = self.peek(1)
            p2 = self.peek(2)
            if not (p1 and p1.type == TokenType.IDENTIFIER and p2 and
                    (p2.type == TokenType.ASSIGN or p2.type == TokenType.DOT or
                     p2.type == TokenType.LBRACKET)):
                return None

        # For '[', we need to speculatively parse and check for ']' followed
        # by '=' or another designator.  Save position for backtracking.
        if self._at(TokenType.LBRACKET):
            saved_pos = self.position
            saved_tok = self.current_token
            # Try to parse [expr] and check what follows
            self.advance()  # consume '['
            # Skip tokens until we find matching ']' (handle nesting)
            depth = 1
            while depth > 0 and not self._at(TokenType.EOF):
                if self._at(TokenType.LBRACKET):
                    depth += 1
                elif self._at(TokenType.RBRACKET):
                    depth -= 1
                    if depth == 0:
                        break
                self.advance()
            if depth != 0:
                # Unmatched bracket, restore and return None
                self.position = saved_pos
                self.current_token = saved_tok
                return None
            # We're at ']', peek past it
            after_bracket = self.peek(1)
            # Restore position regardless - we'll re-parse properly below
            self.position = saved_pos
            self.current_token = saved_tok
            if not (after_bracket and
                    (after_bracket.type == TokenType.ASSIGN or
                     after_bracket.type == TokenType.DOT or
                     after_bracket.type == TokenType.LBRACKET)):
                return None

        head = self._parse_designator_chain()
        if head is not None:
            self._expect(TokenType.ASSIGN, "Expected '=' after designator")
        return head

    def _parse_designator_chain(self) -> Optional[Designator]:
        """Parse a chain of designators (.a.b[i].c etc.)."""
        first = self._parse_single_designator()
        if first is None:
            return None

        # Parse additional chained designators
        tail = first
        while self._at(TokenType.DOT) or self._at(TokenType.LBRACKET):
            nxt = self._parse_single_designator()
            if nxt is None:
                break
            tail.next = nxt
            tail = nxt

        return first

    def _parse_single_designator(self) -> Optional[Designator]:
        """Parse a single designator: .member or [index]."""
        tok = self.current_token
        if tok is None:
            return None

        if self._at(TokenType.DOT):
            # .member designator
            # Peek to confirm next is IDENTIFIER (not ELLIPSIS etc.)
            p = self.peek(1)
            if not (p and p.type == TokenType.IDENTIFIER):
                return None
            dot_tok = tok
            self.advance()  # consume '.'
            member_tok = self._expect(TokenType.IDENTIFIER, "Expected member name after '.'")
            return Designator(member=member_tok.value, line=dot_tok.line, column=dot_tok.column)

        if self._at(TokenType.LBRACKET):
            # [index] designator
            bracket_tok = tok
            self.advance()  # consume '['
            index_expr = self._parse_conditional()
            self._expect(TokenType.RBRACKET, "Expected ']' after array designator index")
            return Designator(index=index_expr, line=bracket_tok.line, column=bracket_tok.column)

        return None

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
                    result = self._parse_local_declaration()
                    if isinstance(result, list):
                        init = result[0]  # for-init: use first declarator
                    else:
                        init = result
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

    # Expressions (precedence climbing)

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
                    self._skip_pointer_qualifiers()
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
        if tok and tok.type == TokenType.INCREMENT:
            self.advance()
            operand = self._parse_unary()
            return UnaryOp(operator="++", operand=operand, is_postfix=False, line=tok.line, column=tok.column)
        if tok and tok.type == TokenType.DECREMENT:
            self.advance()
            operand = self._parse_unary()
            return UnaryOp(operator="--", operand=operand, is_postfix=False, line=tok.line, column=tok.column)
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
            if self.current_token and self.current_token.type == TokenType.INCREMENT:
                tok_inc = self.current_token
                self.advance()
                expr = UnaryOp(operator="++", operand=expr, is_postfix=True, line=tok_inc.line, column=tok_inc.column)
                continue
            if self.current_token and self.current_token.type == TokenType.DECREMENT:
                tok_dec = self.current_token
                self.advance()
                expr = UnaryOp(operator="--", operand=expr, is_postfix=True, line=tok_dec.line, column=tok_dec.column)
                continue
            break
        return expr

    def _parse_primary(self):
        tok = self.current_token
        if tok is None:
            raise ParserError("Unexpected end of input")

        # ── GCC extension: __builtin_va_arg(ap, type) ──────────────────
        # When using system cpp (gcc -E), the standard va_arg(ap, T) macro
        # is expanded to __builtin_va_arg(ap, T).  Unlike a normal function
        # call, the second argument is a *type name*, not an expression.
        # We parse it here and rewrite to the internal __builtin_va_arg_int
        # call that codegen already understands.
        if (tok.type == TokenType.IDENTIFIER
                and tok.value == "__builtin_va_arg"):
            self.advance()  # consume '__builtin_va_arg'
            self._expect(TokenType.LPAREN, "Expected '(' after __builtin_va_arg")
            ap_expr = self._parse_assignment()
            self._expect(TokenType.COMMA, "Expected ',' in __builtin_va_arg")
            # Parse the type argument (second arg is a type name, not expr).
            _va_type = self._parse_type_specifier()
            while self._match(TokenType.STAR):
                _va_type.pointer_level = int(getattr(_va_type, "pointer_level", 0)) + 1
                _va_type._normalize_pointer_state()
            self._expect(TokenType.RPAREN, "Expected ')' after __builtin_va_arg")
            # Rewrite to __builtin_va_arg_int(ap) — the internal form that
            # codegen handles.  Currently only GP (int/long/pointer) types
            # are supported; float va_arg would need a separate builtin.
            fn = Identifier(name="__builtin_va_arg_int",
                            line=tok.line, column=tok.column)
            return FunctionCall(function=fn, arguments=[ap_expr],
                                line=tok.line, column=tok.column)

        # ── GCC extension: __builtin_va_end(ap) ───────────────────────
        # System cpp expands va_end(ap) to __builtin_va_end(ap).
        # This is already handled as a normal function call by codegen,
        # but we need to make sure the identifier passes through.
        # (No special parsing needed — falls through to generic IDENTIFIER.)

        # ── GCC extension: __builtin_va_start(ap, last) ───────────────
        # System cpp expands va_start(ap, last) to __builtin_va_start(ap).
        # Also handled as a normal function call by codegen.
        # (No special parsing needed — falls through to generic IDENTIFIER.)

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
            value = tok.value
            while self.current_token and self.current_token.type == TokenType.STRING:
                value += self.current_token.value
                self.advance()
            return StringLiteral(value=value, line=tok.line, column=tok.column)
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
                    # Pointer qualifiers after each '*': (const char *const *)
                    self._skip_pointer_qualifiers()
                # Function pointer cast: (type (*)(params))expr
                # After consuming the base type and any pointer stars, if we
                # see '(' it may be a function pointer type cast like
                # (int(*)(void)) or (uid_t(*)(int,int)).
                if self._at(TokenType.LPAREN) and self.peek(1) and self.peek(1).type == TokenType.STAR:
                    self.advance()  # consume '('
                    self.advance()  # consume '*'
                    # Consume additional pointer stars: (**)(params) means
                    # pointer-to-function-pointer cast.
                    while self._match(TokenType.STAR):
                        pass
                    self._skip_pointer_qualifiers()
                    self._expect(TokenType.RPAREN, "Expected ')' in function pointer cast")
                    # Consume parameter list
                    if self._match(TokenType.LPAREN):
                        depth = 1
                        while self.current_token and depth > 0:
                            if self._at(TokenType.LPAREN):
                                depth += 1
                            elif self._at(TokenType.RPAREN):
                                depth -= 1
                                if depth == 0:
                                    break
                            self.advance()
                        self._expect(TokenType.RPAREN, "Expected ')' after cast parameter list")
                    ty = Type(base=f"{ty.base} (*)()", is_pointer=True,
                              line=ty.line, column=ty.column)
                    ty._normalize_pointer_state()
                self._expect(TokenType.RPAREN, "Expected ')' after cast type")
                expr = self._parse_unary()
                return Cast(type=ty, expression=expr, line=tok.line, column=tok.column)
            expr = self._parse_expression()
            self._expect(TokenType.RPAREN, "Expected ')' ")
            return expr

        raise ParserError("Expected expression", tok)
