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
        CommaOp,
        Expression,
        Type,
        MemberAccess,
        PointerMemberAccess,
    Cast,
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
    # Kind of global declaration/definition per TU (subset):
    # - "extern_decl": `extern int g;`
    # - "tentative": `int g;`
    # - "definition": `int g = 1;`
    # - "internal": `static int g;` (any form)
    global_kinds: Dict[str, str]
    # Best-effort function signature info (subset)
    # name -> (return_base, param_count or None, is_variadic)
    function_sigs: Dict[str, tuple[str, Optional[int], bool]]
    # Global arrays: name -> (element_base, element_count)
    global_arrays: Dict[str, tuple[str, int]]


class SemanticError(Exception):
    """Semantic analysis error"""
    def __init__(self, message: str, token=None):
        super().__init__(message)
        self.token = token


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
        self._global_kinds: Dict[str, str] = {}

        self._global_types: Dict[str, str] = {}
        # Preserve Type nodes for globals so we can check qualifiers like const.
        self._global_decl_types: Dict[str, Type] = {}
        self._enum_constants: Dict[str, int] = {}
        self._global_arrays: Dict[str, tuple[str, int]] = {}

        seen_globals: Dict[str, str] = {}
        # Minimal function redeclaration compatibility tracking (C89 subset).
        # Map: function name -> (return_type_base, param_count or None if unspecified)
        func_sigs: Dict[str, tuple[str, Optional[int]]] = {}
        self._function_sigs: Dict[str, tuple[str, Optional[int], bool]] = {}

        for decl in ast.declarations:
            if isinstance(decl, FunctionDecl):
                # C89 subset: if we have multiple prototypes/decls for the same
                # function name, require return type base and parameter count to match
                # (when parameters are specified).
                ret_base = getattr(decl, "return_type", None)
                ret_base_s = getattr(ret_base, "base", "int") if ret_base is not None else "int"
                # Parser always provides a list; treat empty list as specified (0 params).
                param_count: Optional[int] = len(getattr(decl, "parameters", []) or [])
                prev = func_sigs.get(decl.name)
                if prev is None:
                    func_sigs[decl.name] = (str(ret_base_s), param_count)
                else:
                    prev_ret, prev_n = prev
                    if str(ret_base_s) != prev_ret:
                        self.errors.append(f"conflicting return type for function '{decl.name}'")
                    # If both sides have an explicit parameter list, require same count.
                    if prev_n is not None and param_count is not None and prev_n != param_count:
                        self.errors.append(f"conflicting parameter count for function '{decl.name}'")
                self._declare_global(decl.name, "function")
                self._functions.add(decl.name)
                # Record function type for codegen. We don't model full
                # prototypes yet, but we need to know whether it's variadic.
                # Encode as a simple string so codegen can check for "...".

                # Record function signature info for multi-TU driver checks.
                try:
                    ret_base = getattr(decl, "return_type", None)
                    ret_base_s = getattr(ret_base, "base", "int") if ret_base is not None else "int"
                    params = getattr(decl, "parameters", []) or []
                    param_count: Optional[int] = len(params)
                    is_variadic = bool(getattr(decl, "is_variadic", False)) or any(
                        getattr(p, "name", None) == "..." for p in params
                    )
                    self._function_sigs[decl.name] = (str(ret_base_s), param_count, is_variadic)
                except Exception:
                    self._function_sigs[decl.name] = ("int", None, False)
                try:
                    ret_base = getattr(decl, "return_type", None)
                    ret_base_s = getattr(ret_base, "base", "int") if ret_base is not None else "int"
                    params = getattr(decl, "parameters", []) or []
                    is_variadic = bool(getattr(decl, "is_variadic", False)) or any(
                        getattr(p, "name", None) == "..." for p in params
                    )
                    self._global_types[decl.name] = (
                        f"function {ret_base_s}(... )" if is_variadic else f"function {ret_base_s}"
                    )
                except Exception:
                    self._global_types[decl.name] = "function int"
                # Record linkage for function declarations.
                sc = getattr(decl, "storage_class", None)
                if sc == "static":
                    self._global_linkage[decl.name] = "internal"
                else:
                    # extern or default
                    self._global_linkage[decl.name] = "external"
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
                # C89: objects cannot have type void.
                if getattr(decl, "type", None) is not None and getattr(decl.type, "base", None) == "void":
                    self.errors.append(f"variable '{decl.name}' declared with type void")
                # C89: `extern` is a declaration; it cannot have an initializer.
                if sc == "extern" and getattr(decl, "initializer", None) is not None:
                    self.errors.append(f"extern declaration cannot have an initializer: '{decl.name}'")
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

                # Record kind for multi-TU validation (subset).
                if sc == "static":
                    self._global_kinds[decl.name] = "internal"
                elif sc == "extern":
                    self._global_kinds[decl.name] = "extern_decl"
                else:
                    self._global_kinds[decl.name] = "definition" if getattr(decl, "initializer", None) is not None else "tentative"
                # record declared base type string for codegen (e.g. "int", "char", "struct S*", etc.)
                try:
                    # `decl.type` is a Type node; its `is_pointer` determines pointer-ness.
                    # Record a normalized string so codegen can cheaply detect pointers.
                    if getattr(decl.type, "is_pointer", False):
                        self._global_types[decl.name] = f"{decl.type.base}*"
                    else:
                        self._global_types[decl.name] = str(decl.type.base)
                    # keep full Type node (incl. qualifiers)
                    self._global_decl_types[decl.name] = decl.type
                except Exception:
                    self._global_types[decl.name] = "int"

                # Record global array element type and count when available.
                # Parser encodes arrays via Declaration.array_size.
                try:
                    n = getattr(decl, "array_size", None)
                    if n is not None:
                        self._global_arrays[decl.name] = (str(getattr(decl.type, "base", "int")), int(n))
                    # Infer `char s[] = "...";` size when unsized and initialized.
                    if (
                        n is None
                        and not getattr(decl.type, "is_pointer", False)
                        and getattr(decl.type, "base", None) in {"char", "unsigned char"}
                        and getattr(decl, "initializer", None) is not None
                    ):
                        init = getattr(decl, "initializer")
                        if isinstance(init, StringLiteral):
                            self._global_arrays[decl.name] = (str(getattr(decl.type, "base", "char")), len(init.value) + 1)
                except Exception:
                    pass

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
            global_kinds=dict(self._global_kinds),
            function_sigs=dict(self._function_sigs),
            global_arrays=dict(self._global_arrays),
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
        if isinstance(expr, CommaOp):
            # Constant expressions may include the comma operator; the value is the RHS.
            self._eval_const_int(expr.left)
            return self._eval_const_int(expr.right)
        if isinstance(expr, TernaryOp):
            c = self._eval_const_int(expr.condition)
            return self._eval_const_int(expr.true_expr if c != 0 else expr.false_expr)
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
        if isinstance(expr, BinaryOp) and expr.operator in {"+", "-", "*", "/", "%", "|", "&", "^", "<<", ">>", "<"}:
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
            if expr.operator == "<":
                return 1 if l < r else 0
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
        ty = getattr(self, "_decl_types", {}).get(name)
        if ty is None:
            ty = getattr(self, "_global_decl_types", {}).get(name)
        return ty

    def _is_declared(self, name: str) -> bool:
        for scope in reversed(self._scopes):
            if name in scope:
                return True
        return False

    # -----------------
    # Analyze nodes
    # -----------------

    def _analyze_function(self, fn: FunctionDecl) -> None:
        # Ensure function locals/params are declared in a scope that remains
        # active for the whole function body analysis.
        self._push_scope()
        # reset per-function declared-type table
        self._decl_types = {}
        # function-scoped labels (C89)
        self._labels_defined: Set[str] = set()
        self._labels_gotoed: Set[str] = set()
        # best-effort map of identifier -> declared Type
        for p in fn.parameters:
            # C89: parameter of type void is invalid (except sole parameter list 'void').
            if getattr(p, "type", None) is not None and getattr(p.type, "base", None) == "void":
                self.errors.append(f"parameter '{p.name}' declared with type void")
            self._declare_local(p.name, "param")
            self._decl_types[p.name] = p.type
        # track register locals so we can reject `&register_var` (C89 rule)
        self._register_locals: Set[str] = set()
        # Analyze the function body *without* introducing an extra nested
        # scope for the outermost compound statement, so locals declared in the
        # body stay visible across all statements.
        if isinstance(fn.body, CompoundStmt):
            for item in fn.body.statements:
                if isinstance(item, Declaration):
                    self._declare_local(item.name, "variable")
                    self._decl_types[item.name] = item.type
                    # If this is a local `extern` declaration of a function prototype,
                    # record it in global tables so codegen can treat calls as
                    # direct calls and apply variadic ABI rules.
                    if getattr(item, "storage_class", None) == "extern":
                        try:
                            base = getattr(item.type, "base", None)
                            # Parser encodes function types in Type.base like: "int (*)()".
                            if isinstance(base, str) and "(" in base and ")" in base:
                                # best-effort: mark as function
                                # NOTE: variadic detection relies on the parser's sentinel param name '...'
                                # which is not represented in this local Declaration; keep non-variadic.
                                self._global_types[item.name] = f"function {base.split()[0]}"
                                self._global_linkage[item.name] = "external"
                                self._functions.add(item.name)
                        except Exception:
                            pass
                    if getattr(item, "storage_class", None) == "register":
                        self._register_locals.add(item.name)
                    if getattr(item, "storage_class", None) == "extern" and item.initializer is not None:
                        self.errors.append(f"extern declaration cannot have an initializer: '{item.name}'")
                    if item.initializer is not None:
                        self._analyze_expr(item.initializer)
                else:
                    self._analyze_stmt(item)
        else:
            self._analyze_stmt(fn.body)
        missing = sorted(self._labels_gotoed - self._labels_defined)
        for m in missing:
            self.errors.append(f"Undefined label '{m}'")
        # Keep locals/params visible throughout analysis; pop now that we're
        # done analyzing the entire function.
        self._pop_scope()

    def _analyze_stmt(self, stmt: Statement) -> None:
        if isinstance(stmt, CompoundStmt):
            self._push_scope()
            for item in stmt.statements:
                if isinstance(item, Declaration):
                    self._declare_local(item.name, "variable")
                    self._decl_types[item.name] = item.type
                    if getattr(item, "storage_class", None) == "register":
                        self._register_locals.add(item.name)
                    # local `static` is supported (subset); handled by IR/codegen as a global-like symbol.
                    # C89: `extern` is a declaration; it cannot have an initializer.
                    if getattr(item, "storage_class", None) == "extern" and item.initializer is not None:
                        self.errors.append(f"extern declaration cannot have an initializer: '{item.name}'")
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
                if getattr(stmt.init, "storage_class", None) == "register":
                    self._register_locals.add(stmt.init.name)
                # local `static` is supported (subset); handled by IR/codegen as a global-like symbol.
                # C89: `extern` is a declaration; it cannot have an initializer.
                if getattr(stmt.init, "storage_class", None) == "extern" and stmt.init.initializer is not None:
                    self.errors.append(f"extern declaration cannot have an initializer: '{stmt.init.name}'")
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
            # Best-effort: treat names with known declared types as declared.
            if self._lookup_decl_type(expr.name) is None and not self._is_declared(expr.name):
                # C89 implicit extern/implicit int isn't desired for variables.
                # But allow unknown names if they are used as function identifiers.
                self.errors.append(f"Use of undeclared identifier: {expr.name}")
            return

        if isinstance(expr, BinaryOp):
            # Ensure identifiers are validated before we do operator checks that
            # require type lookup.
            self._analyze_expr(expr.left)
            self._analyze_expr(expr.right)

            def _is_ptrlike(e: Expression) -> bool:
                if isinstance(e, Identifier):
                    ty = self._lookup_decl_type(e.name)
                    if ty is None:
                        return False
                    return bool(getattr(ty, "is_pointer", False))
                if isinstance(e, Cast):
                    to_ty = getattr(e, "to_type", None)
                    return bool(to_ty is not None and getattr(to_ty, "is_pointer", False))
                # Handle simple pointer expressions like `a + 1`.
                if isinstance(e, BinaryOp) and e.operator in {"+", "-"}:
                    return _is_ptrlike(e.left) or _is_ptrlike(e.right)
                return False

            def _is_void_ptr(e: Expression) -> bool:
                if isinstance(e, Identifier):
                    ty = getattr(self, "_decl_types", {}).get(e.name)
                    if ty is None:
                        ty = getattr(self, "_global_decl_types", {}).get(e.name)
                    return bool(
                        ty is not None
                        and getattr(ty, "is_pointer", False)
                        and getattr(ty, "base", None) == "void"
                    )
                if isinstance(e, Cast):
                    to_ty = getattr(e, "to_type", None)
                    return bool(
                        to_ty is not None
                        and getattr(to_ty, "is_pointer", False)
                        and getattr(to_ty, "base", None) == "void"
                    )
                return False

            # C89/C99: pointer arithmetic on void* is not allowed.
            # Best-effort: reject `void* +/- integer` and `integer +/- void*`.
            if expr.operator in {"+", "-"}:
                if _is_void_ptr(expr.left) or _is_void_ptr(expr.right):
                    self.errors.append("void* pointer arithmetic is not allowed")

            # C89/C99: pointer + pointer is not allowed (only pointer +/- integer,
            # and pointer - pointer). Catch identifiers, casts, and arrays which
            # decay to pointers in most expressions.
            if expr.operator == "+":
                # Detect any pointer-like expression on the left/right.
                if _is_ptrlike(expr.left) and _is_ptrlike(expr.right):
                    self.errors.append("pointer + pointer is not allowed")

            # Conservative: relational comparisons require either two pointers
            # (typically within the same aggregate/object) or two arithmetic
            # values. We enforce a minimal subset:
            # - reject pointer vs non-pointer relational compares
            # - reject relational compares on void* (lack of element type)
            if expr.operator in {"<", "<=", ">", ">="}:
                lp = _is_ptrlike(expr.left)
                rp = _is_ptrlike(expr.right)
                if lp != rp:
                    # Allow relational comparisons on ptrdiff-like integer
                    # expressions produced by `ptr - ptr` in this MVP.
                    def _is_ptrdiff_like(e: Expression) -> bool:
                        return (
                            isinstance(e, BinaryOp)
                            and e.operator == "-"
                            and _is_ptrlike(e.left)
                            and (
                                _is_ptrlike(e.right)
                                or isinstance(e.right, Identifier)  # array identifier decay subset
                            )
                        )

                    if _is_ptrdiff_like(expr.left) or _is_ptrdiff_like(expr.right):
                        pass
                    else:
                        self.errors.append(f"pointer and non-pointer comparison is not allowed: '{expr.operator}'")
                elif lp and rp and (_is_void_ptr(expr.left) or _is_void_ptr(expr.right)):
                    self.errors.append("relational comparison on void* pointer is not allowed")

            # Conservative: for equality comparisons, allow:
            # - pointer ==/!= pointer (including void*)
            # - pointer ==/!= 0 (null pointer constant subset)
            # Reject pointer ==/!= non-zero integers.
            if expr.operator in {"==", "!="}:
                lp = _is_ptrlike(expr.left)
                rp = _is_ptrlike(expr.right)

                def _is_zero_int_const(e: Expression) -> bool:
                    if isinstance(e, IntLiteral):
                        try:
                            return int(e.value) == 0
                        except Exception:
                            return False
                    if isinstance(e, Cast):
                        # allow (int)0 etc.
                        return _is_zero_int_const(e.expression)
                    return False

                if lp != rp:
                    # pointer compared to 0 is allowed (null pointer constant subset).
                    if (lp and _is_zero_int_const(expr.right)) or (rp and _is_zero_int_const(expr.left)):
                        pass
                    # Allow comparing pointers against ptrdiff-like integer expressions
                    # produced by `ptr - ptr` in this MVP.
                    elif (
                        lp
                        and isinstance(expr.left, BinaryOp)
                        and expr.left.operator == "-"
                        and _is_ptrlike(expr.left.left)
                        and _is_ptrlike(expr.left.right)
                    ) or (
                        rp
                        and isinstance(expr.right, BinaryOp)
                        and expr.right.operator == "-"
                        and _is_ptrlike(expr.right.left)
                        and _is_ptrlike(expr.right.right)
                    ):
                        pass
                    # Allow comparisons like (p - a) == 2 where `a` is an array
                    # identifier that decays to a pointer.
                    elif (
                        lp
                        and isinstance(expr.left, BinaryOp)
                        and expr.left.operator == "-"
                        and _is_ptrlike(expr.left.left)
                        and isinstance(expr.left.right, Identifier)
                    ) or (
                        rp
                        and isinstance(expr.right, BinaryOp)
                        and expr.right.operator == "-"
                        and _is_ptrlike(expr.right.left)
                        and isinstance(expr.right.right, Identifier)
                    ):
                        pass
                    else:
                        self.errors.append(f"pointer and non-pointer equality comparison is not allowed: '{expr.operator}'")

            # Best-effort: reject subtraction of pointers with obviously
            # different base types (e.g. int* - char*).
            if expr.operator == "-":
                def _ptr_base(e: Expression) -> Optional[str]:
                    if isinstance(e, Identifier):
                        ty = self._lookup_decl_type(e.name)
                        if ty is None or not getattr(ty, "is_pointer", False):
                            return None
                        return str(getattr(ty, "base", ""))
                    if isinstance(e, Cast):
                        to_ty = getattr(e, "to_type", None)
                        if to_ty is None or not getattr(to_ty, "is_pointer", False):
                            return None
                        return str(getattr(to_ty, "base", ""))
                    return None

                lb = _ptr_base(expr.left)
                rb = _ptr_base(expr.right)
                if lb is not None and rb is not None and lb != rb:
                    self.errors.append("pointer - pointer with different base types is not allowed")

            # Ensure we still analyze nested expressions for other checks.

            return

        if isinstance(expr, Cast):
            # Analyze the inner expression; type-checking is minimal for now.
            self._analyze_expr(expr.expression)
            return

        if isinstance(expr, UnaryOp):
            # C89: cannot take the address of a register object.
            if expr.operator == "&" and isinstance(expr.operand, Identifier):
                if expr.operand.name in getattr(self, "_register_locals", set()):
                    self.errors.append(
                        f"Cannot take address of register variable '{expr.operand.name}' at {expr.operand.line}:{expr.operand.column}"
                    )
            # Also reject taking the address of any subobject of a register
            # object (e.g. `&s.x` where `s` is `register struct S s;`).
            if expr.operator == "&" and not isinstance(expr.operand, Identifier):
                from pycc.ast_nodes import MemberAccess as _MemberAccess, PointerMemberAccess as _PointerMemberAccess

                def _base_ident(e: Expression):
                    # Peel member access chains: s.x.y -> Identifier('s')
                    while isinstance(e, (_MemberAccess, _PointerMemberAccess)):
                        e = e.object if isinstance(e, _MemberAccess) else e.pointer
                    return e if isinstance(e, Identifier) else None

                b = _base_ident(expr.operand)
                if b is not None and b.name in getattr(self, "_register_locals", set()):
                    self.errors.append(
                        f"Cannot take address of register variable '{b.name}' at {b.line}:{b.column}"
                    )
            if expr.operator == "+":
                def _is_ptrlike(e: Expression) -> bool:
                    if isinstance(e, Identifier):
                        ty = self._lookup_decl_type(e.name)
                        if ty is None:
                            return False
                        return bool(getattr(ty, "is_pointer", False))
                    if isinstance(e, Cast):
                        to_ty = getattr(e, "to_type", None)
                        return bool(to_ty is not None and getattr(to_ty, "is_pointer", False))
                    # Handle simple pointer expressions like `a + 1`.
                    if isinstance(e, BinaryOp) and e.operator in {"+", "-"}:
                        return _is_ptrlike(e.left) or _is_ptrlike(e.right)
                    return False
                # Detect any pointer-like expression on the left/right.
                # NOTE: Unary '+' only has one operand; pointer+pointer is a BinaryOp check.
            self._analyze_expr(expr.operand)
            return

        if isinstance(expr, Assignment):
            # C89 subset: reject assignment to const-qualified locals.
            if isinstance(expr.target, Identifier):
                ty = getattr(self, "_decl_types", {}).get(expr.target.name)
                if ty is None:
                    ty = getattr(self, "_global_decl_types", {}).get(expr.target.name)
                if getattr(ty, "is_const", False):
                    self.errors.append(f"Assignment to const-qualified variable '{expr.target.name}'")

            # Feature B (subset): reject writes through pointers-to-const.
            # Detect `*p = ...` where `p` was declared as `const T*`.
            if isinstance(expr.target, UnaryOp) and expr.target.operator == "*" and isinstance(expr.target.operand, Identifier):
                p_name = expr.target.operand.name
                p_ty = getattr(self, "_decl_types", {}).get(p_name)
                if p_ty is not None and getattr(p_ty, "is_pointer", False) and getattr(p_ty, "is_const", False):
                    self.errors.append(f"Assignment through pointer to const is not allowed: '*{p_name}'")

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

        if isinstance(expr, CommaOp):
            self._analyze_expr(expr.left)
            self._analyze_expr(expr.right)
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
