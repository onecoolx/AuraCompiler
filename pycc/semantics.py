"""pycc.semantics

Minimal semantic analysis for the current project stage.

Goals (MVP):
- scope tracking (global / function / block)
- record variable declarations
- allow implicit function declarations (C89 style) for external calls like printf
- basic checks: duplicate declarations in same scope, undefined identifiers in
    expressions (best-effort)

This is intentionally conservative; full C99 type system will be added later.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Union, Tuple

from pycc.ast_nodes import (
        Program,
        Declaration,
        FunctionDecl,
    TypedefDecl,
    StructDecl,
    UnionDecl,
    EnumDecl,
        CompoundStmt,
        Statement,
        ExpressionStmt,
        IfStmt,
        WhileStmt,
        DoWhileStmt,
        ForStmt,
        ReturnStmt,
        BreakStmt,
        ContinueStmt,
        GotoStmt,
        LabelStmt,
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
        Expression,
        Type,
        MemberAccess,
        PointerMemberAccess,
)


@dataclass
class StructLayout:
    kind: str  # "struct" or "union"
    name: str
    size: int
    align: int
    member_offsets: Dict[str, int]
    member_sizes: Dict[str, int]


@dataclass
class SemanticContext:
    typedefs: Dict[str, Type]
    layouts: Dict[str, StructLayout]  # key: "struct Tag" / "union Tag"
    global_types: Dict[str, str]
    global_linkage: Dict[str, str]


class SemanticError(Exception):
    """Semantic analysis error"""
    pass


class SemanticAnalyzer:
    """Semantic analyzer for C99"""
    
    def __init__(self):
        # A simple scope stack: list of dict(name -> kind)
        self._scopes: List[Dict[str, str]] = [{}]
        # typedef scope stack: list of dict(name -> Type)
        self._typedefs: List[Dict[str, Type]] = [{}]
        self.errors: List[str] = []
        self.warnings: List[str] = []
        # Track globally known functions (including implicit decls)
        self._functions: Set[str] = set()
        self._layouts: Dict[str, StructLayout] = {}
    
    def analyze(self, ast: Program) -> SemanticContext:
        """Analyze AST for semantic errors"""
        self.errors = []
        self.warnings = []
        self._scopes = [{}]
        self._functions = set()
        self._typedefs = [{}]
        self._layouts = {}
        self._global_linkage: Dict[str, str] = {}

        self._global_types: Dict[str, str] = {}
        self._enum_constants: Dict[str, int] = {}

        seen_globals: Dict[str, str] = {}

        for decl in ast.declarations:
            if isinstance(decl, FunctionDecl):
                self._declare_global(decl.name, "function")
                self._functions.add(decl.name)
            elif isinstance(decl, EnumDecl):
                self._register_enum_decl(decl)
            elif isinstance(decl, TypedefDecl):
                # register typedef in global typedefs
                self._declare_typedef_global(decl.name, decl.type)
            elif isinstance(decl, (StructDecl, UnionDecl)):
                self._register_layout_decl(decl)
            elif isinstance(decl, Declaration):
                if decl.name == "__tagdecl__":
                    # struct/union tag-only declarations are ignored in MVP
                    continue
                # minimal duplicate/ABI checks for globals
                sc = getattr(decl, "storage_class", None)
                kind = "static" if sc == "static" else "nonstatic"
                prev = seen_globals.get(decl.name)
                if prev is not None and prev != kind:
                    self.errors.append(f"conflicting linkage for global '{decl.name}'")
                else:
                    seen_globals[decl.name] = kind

                self._declare_global(decl.name, "variable")
                # record linkage (minimal, single TU): static = internal, otherwise external
                if sc == "static":
                    self._global_linkage[decl.name] = "internal"
                else:
                    self._global_linkage[decl.name] = "external"
                # record declared base type string for codegen (e.g. "int", "char", "struct S*", etc.)
                try:
                    # `decl.type` is a Type node; its `is_pointer` determines pointer-ness.
                    # Record a normalized string so codegen can cheaply detect pointers.
                    if getattr(decl.type, "is_pointer", False):
                        self._global_types[decl.name] = f"{decl.type.base}*"
                    else:
                        self._global_types[decl.name] = str(decl.type.base)
                except Exception:
                    self._global_types[decl.name] = "int"

        for decl in ast.declarations:
            if isinstance(decl, FunctionDecl) and decl.body is not None:
                self._analyze_function(decl)
            elif isinstance(decl, Declaration) and decl.initializer is not None:
                self._analyze_expr(decl.initializer)
            elif isinstance(decl, TypedefDecl):
                # typedef has no further analysis
                pass
            elif isinstance(decl, EnumDecl):
                # already processed
                pass

        if self.errors:
            raise SemanticError("\n".join(self.errors))
        # flatten typedefs (global scope only for now)
        return SemanticContext(
            typedefs=dict(self._typedefs[0]),
            layouts=dict(self._layouts),
            global_types=dict(self._global_types),
            global_linkage=dict(self._global_linkage),
        )

    def _register_enum_decl(self, decl: EnumDecl) -> None:
        cur = -1
        for name, val_expr in (decl.enumerators or []):
            if val_expr is None:
                cur += 1
            else:
                cur = self._eval_const_int(val_expr)
            self._enum_constants[name] = cur
            # Treat enum constants as declared names in the global scope.
            self._scopes[0].setdefault(name, "enum_const")

    def _eval_const_int(self, expr: Expression) -> int:
        # Minimal constant expression evaluator for enum values (C89 subset)
        if isinstance(expr, IntLiteral):
            return int(expr.value)
        if isinstance(expr, CharLiteral):
            return ord(expr.value)
        if isinstance(expr, UnaryOp) and expr.operator in {"+", "-", "~"}:
            v = self._eval_const_int(expr.operand)
            if expr.operator == "+":
                return v
            if expr.operator == "-":
                return -v
            return ~v
        if isinstance(expr, BinaryOp) and expr.operator in {"+", "-", "*", "/", "%", "|", "&", "^", "<<", ">>"}:
            l = self._eval_const_int(expr.left)
            r = self._eval_const_int(expr.right)
            if expr.operator == "+":
                return l + r
            if expr.operator == "-":
                return l - r
            if expr.operator == "*":
                return l * r
            if expr.operator == "/":
                return int(l / r)
            if expr.operator == "%":
                return l % r
            if expr.operator == "|":
                return l | r
            if expr.operator == "&":
                return l & r
            if expr.operator == "^":
                return l ^ r
            if expr.operator == "<<":
                return l << r
            return l >> r
        if isinstance(expr, Identifier) and expr.name in self._enum_constants:
            return self._enum_constants[expr.name]
        raise SemanticError("enum value must be an integer constant expression")

    def _register_layout_decl(self, decl: Union[StructDecl, UnionDecl]) -> None:
        kind = "struct" if isinstance(decl, StructDecl) else "union"
        tag = decl.name
        if not tag:
            return
        key = f"{kind} {tag}"
        if key in self._layouts and decl.members is None:
            return
        if decl.members is None:
            # forward decl
            self._layouts.setdefault(key, StructLayout(kind=kind, name=tag, size=0, align=1, member_offsets={}, member_sizes={}))
            return
        layout = self._compute_layout(kind, tag, decl.members)
        self._layouts[key] = layout

    def _compute_layout(self, kind: str, tag: str, members: List[Declaration]) -> StructLayout:
        # MVP: only handle members of builtin int/char and pointers.
        offsets: Dict[str, int] = {}
        sizes: Dict[str, int] = {}

        def size_align(ty: Type) -> Tuple[int, int]:
            if ty.is_pointer:
                return 8, 8
            if ty.base == "int":
                return 4, 4
            if ty.base == "char":
                return 1, 1
            # unknown types treated as 8-byte
            return 8, 8

        off = 0
        max_align = 1
        max_size = 0

        for m in members:
            sz, al = size_align(m.type)
            max_align = max(max_align, al)
            if kind == "struct":
                # align current offset
                if off % al != 0:
                    off += (al - (off % al))
                offsets[m.name] = off
                sizes[m.name] = sz
                off += sz
                max_size = off
            else:
                # union members all offset 0
                offsets[m.name] = 0
                sizes[m.name] = sz
                max_size = max(max_size, sz)

        size = max_size
        # final struct size align
        if kind == "struct" and size % max_align != 0:
            size += (max_align - (size % max_align))

        return StructLayout(kind=kind, name=tag, size=size, align=max_align, member_offsets=offsets, member_sizes=sizes)

    # -----------------
    # Scopes
    # -----------------

    def _push_scope(self) -> None:
        self._scopes.append({})
        self._typedefs.append({})

    def _pop_scope(self) -> None:
        self._scopes.pop()
        self._typedefs.pop()

    def _declare_global(self, name: str, kind: str) -> None:
        # Minimal C89: allow repeated global declarations of the same kind
        # (e.g. `extern int g;` followed by `int g = 1;` in the same TU).
        prev = self._scopes[0].get(name)
        if prev is None:
            self._scopes[0][name] = kind
            return
        if prev != kind:
            self.errors.append(f"Duplicate global declaration: {name}")

    def _declare_typedef_global(self, name: str, ty: Type) -> None:
        if name in self._typedefs[0]:
            self.errors.append(f"Duplicate typedef: {name}")
        else:
            self._typedefs[0][name] = ty

    def _declare_typedef_local(self, name: str, ty: Type) -> None:
        if name in self._typedefs[-1]:
            self.errors.append(f"Duplicate typedef in scope: {name}")
        else:
            self._typedefs[-1][name] = ty

    def _lookup_typedef(self, name: str) -> Optional[Type]:
        for td in reversed(self._typedefs):
            if name in td:
                return td[name]
        return None

    def _declare_local(self, name: str, kind: str) -> None:
        if name in self._scopes[-1]:
            self.errors.append(f"Duplicate declaration in scope: {name}")
        else:
            self._scopes[-1][name] = kind

    def _lookup_decl_type(self, name: str) -> Optional[Type]:
        # Best-effort: types are recorded in a side table during statement analysis.
        return getattr(self, "_decl_types", {}).get(name)

    def _is_declared(self, name: str) -> bool:
        for scope in reversed(self._scopes):
            if name in scope:
                return True
        return False

    # -----------------
    # Analyze nodes
    # -----------------

    def _analyze_function(self, fn: FunctionDecl) -> None:
        self._push_scope()
        # function-scoped labels (C89)
        self._labels_defined: Set[str] = set()
        self._labels_gotoed: Set[str] = set()
        # best-effort map of identifier -> declared Type
        if not hasattr(self, "_decl_types"):
            self._decl_types = {}
        for p in fn.parameters:
            self._declare_local(p.name, "param")
            self._decl_types[p.name] = p.type
        self._analyze_stmt(fn.body)
        missing = sorted(self._labels_gotoed - self._labels_defined)
        for m in missing:
            self.errors.append(f"Undefined label '{m}'")
        self._pop_scope()

    def _analyze_stmt(self, stmt: Statement) -> None:
        if isinstance(stmt, CompoundStmt):
            self._push_scope()
            for item in stmt.statements:
                if isinstance(item, Declaration):
                    self._declare_local(item.name, "variable")
                    self._decl_types[item.name] = item.type
                    if item.initializer is not None:
                        self._analyze_expr(item.initializer)
                else:
                    self._analyze_stmt(item)
            self._pop_scope()
            return

        if isinstance(stmt, ExpressionStmt):
            if stmt.expression is not None:
                self._analyze_expr(stmt.expression)
            return

        if isinstance(stmt, IfStmt):
            self._analyze_expr(stmt.condition)
            self._analyze_stmt(stmt.then_stmt)
            if stmt.else_stmt is not None:
                self._analyze_stmt(stmt.else_stmt)
            return

        if isinstance(stmt, WhileStmt):
            self._analyze_expr(stmt.condition)
            self._analyze_stmt(stmt.body)
            return

        if isinstance(stmt, DoWhileStmt):
            self._analyze_stmt(stmt.body)
            self._analyze_expr(stmt.condition)
            return

        if isinstance(stmt, ForStmt):
            self._push_scope()
            if isinstance(stmt.init, Declaration):
                self._declare_local(stmt.init.name, "variable")
                self._decl_types[stmt.init.name] = stmt.init.type
                if stmt.init.initializer is not None:
                    self._analyze_expr(stmt.init.initializer)
            elif stmt.init is not None:
                self._analyze_expr(stmt.init)
            if stmt.condition is not None:
                self._analyze_expr(stmt.condition)
            if stmt.update is not None:
                self._analyze_expr(stmt.update)
            if stmt.body is not None:
                self._analyze_stmt(stmt.body)
            self._pop_scope()
            return

        if isinstance(stmt, ReturnStmt):
            if stmt.value is not None:
                self._analyze_expr(stmt.value)
            return

        if isinstance(stmt, (BreakStmt, ContinueStmt)):
            return

        if isinstance(stmt, LabelStmt):
            self._labels_defined.add(stmt.name)
            self._analyze_stmt(stmt.statement)
            return

        if isinstance(stmt, GotoStmt):
            self._labels_gotoed.add(stmt.label)
            return

        # Unknown statement types are ignored for now

    def _analyze_expr(self, expr: Expression) -> None:
        if isinstance(expr, (IntLiteral, StringLiteral, CharLiteral)):
            return

        if isinstance(expr, Identifier):
            # enum constants are always in-scope as integer constants
            if expr.name in getattr(self, "_enum_constants", {}):
                return
            if not self._is_declared(expr.name):
                # C89 implicit extern/implicit int isn't desired for variables.
                # But allow unknown names if they are used as function identifiers.
                self.errors.append(f"Use of undeclared identifier: {expr.name}")
            return

        if isinstance(expr, BinaryOp):
            self._analyze_expr(expr.left)
            self._analyze_expr(expr.right)
            return

        if isinstance(expr, UnaryOp):
            self._analyze_expr(expr.operand)
            return

        if isinstance(expr, Assignment):
            self._analyze_expr(expr.target)
            self._analyze_expr(expr.value)
            return

        if isinstance(expr, ArrayAccess):
            self._analyze_expr(expr.array)
            self._analyze_expr(expr.index)
            return

        if isinstance(expr, MemberAccess):
            # best-effort: only validate when base is an identifier with known declared type
            if isinstance(expr.object, Identifier):
                base_ty = self._lookup_decl_type(expr.object.name)
                if base_ty is not None:
                    # '.' expects non-pointer struct/union object
                    if base_ty.is_pointer:
                        self.errors.append(f"'.' used on pointer: {expr.object.name}")
                    else:
                        self._validate_member(base_ty, expr.member, expr.object.name)
            else:
                self._analyze_expr(expr.object)
            return

        if isinstance(expr, PointerMemberAccess):
            if isinstance(expr.pointer, Identifier):
                base_ty = self._lookup_decl_type(expr.pointer.name)
                if base_ty is not None:
                    # '->' expects a pointer to struct/union.
                    if not base_ty.is_pointer:
                        self.errors.append(f"'->' used on non-pointer: {expr.pointer.name}")
                    else:
                        # We don't track pointed-to type separately; in this compiler, pointer keeps base_ty.base
                        # and sets is_pointer=True, so base identifies the pointee.
                        pointee = Type(base=base_ty.base, line=base_ty.line, column=base_ty.column)
                        self._validate_member(pointee, expr.member, expr.pointer.name)
            else:
                self._analyze_expr(expr.pointer)
            return

        if isinstance(expr, FunctionCall):
            # If function is identifier and unknown: allow implicit decl.
            if isinstance(expr.function, Identifier):
                if expr.function.name not in self._functions and not self._is_declared(expr.function.name):
                    self._functions.add(expr.function.name)
                    self._declare_global(expr.function.name, "function")
                    self.warnings.append(f"Implicit declaration of function: {expr.function.name}")
            else:
                self._analyze_expr(expr.function)
            for a in expr.arguments:
                self._analyze_expr(a)
            return

        if isinstance(expr, TernaryOp):
            self._analyze_expr(expr.condition)
            self._analyze_expr(expr.true_expr)
            self._analyze_expr(expr.false_expr)
            return

        # Unknown expressions ignored

    def _validate_member(self, base_ty: Type, member: str, base_name: str) -> None:
        # base_ty.base may be like "struct Point" or "union U".
        b = base_ty.base
        if not (isinstance(b, str) and (b.startswith("struct ") or b.startswith("union "))):
            self.errors.append(f"Member access on non-struct/union: {base_name}")
            return
        layout = self._layouts.get(b)
        if layout is None:
            self.errors.append(f"Unknown {b} for member access: {base_name}.{member}")
            return
        if member not in layout.member_offsets:
            self.errors.append(f"No such member '{member}' in {b}")
