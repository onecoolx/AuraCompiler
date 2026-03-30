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

from pycc.ir import _type_size

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
        SizeOf,
)


@dataclass
class StructLayout:
    kind: str  # "struct" or "union"
    name: str
    size: int
    align: int
    member_offsets: Dict[str, int]
    member_sizes: Dict[str, int]
    # Best-effort type strings for members (e.g. "int", "struct S").
    # Used by IR/codegen for nested aggregate handling.
    member_types: Dict[str, str] | None = None


@dataclass
class SemanticContext:
    typedefs: Dict[str, Type]
    layouts: Dict[str, StructLayout]  # key: "struct Tag" / "union Tag"
    global_types: Dict[str, str]
    # Full declared Type nodes for globals (incl. qualifiers/pointerness).
    global_decl_types: Dict[str, Type]
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
    # Optional per-parameter type strings for functions when declared with a prototype.
    # None means non-prototype (`int f();`) or unknown.
    function_param_types: Dict[str, Optional[List[str]]]
    # Global arrays: name -> (element_base, element_count)
    # For globals that are arrays, we track element base type and either:
    # - an int element count (1D), or
    # - a list of dimensions (outer->inner) for multi-dimensional arrays.
    global_arrays: Dict[str, tuple[str, object]]


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
        # Full-ish function redeclaration signature tracking (C89 subset).
        # Map: function name -> list of canonical parameter type strings (or None if unspecified).
        self._function_param_types: Dict[str, Optional[List[str]]] = {}

        for decl in ast.declarations:
            if isinstance(decl, FunctionDecl):
                # C89 subset: if we have multiple prototypes/decls for the same
                # function name, require return type base and parameter count to match
                # (when parameters are specified).
                ret_base = getattr(decl, "return_type", None)
                ret_base_s = getattr(ret_base, "base", "int") if ret_base is not None else "int"
                params_list = list(getattr(decl, "parameters", []) or [])
                # C89: an empty parameter list in a declaration is a non-prototype.
                # Our parser represents `int foo();` as an empty parameters list.
                # Track its count as unspecified (None) for compatibility checks.
                param_count: Optional[int] = len(params_list)
                is_nonprototype_decl = (param_count == 0 and decl.body is None)
                if is_nonprototype_decl:
                    param_count = None
                prev = func_sigs.get(decl.name)
                if prev is None:
                    _pc = param_count
                    # already normalized above
                    func_sigs[decl.name] = (str(ret_base_s), _pc)
                else:
                    prev_ret, prev_n = prev
                    if str(ret_base_s) != prev_ret:
                        self.errors.append(f"conflicting return type for function '{decl.name}'")
                    # If both sides have an explicit parameter list, require same count.
                    cur_n = param_count
                    if prev_n is not None and cur_n is not None and prev_n != cur_n:
                        self.errors.append(f"conflicting parameter count for function '{decl.name}'")

                    # C89 subset: if we saw a non-prototype declaration for this name,
                    # and later we see a prototype with a different arity than a known
                    # definition (or vice-versa), reject.
                    # This is intentionally limited to arity checks.
                    if prev_n is None and cur_n is not None:
                        # prev was non-prototype; keep the prototype arity as the known one.
                        func_sigs[decl.name] = (prev_ret, cur_n)
                    elif prev_n is not None and cur_n is None:
                        # later non-prototype after a prototype is ok; keep prev.
                        pass
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

                # Track per-parameter types for multi-TU checks / future work.
                    self._global_linkage: Dict[str, str] = {}
                    self._global_kinds: Dict[str, str] = {}
                    self._global_types: Dict[str, str] = {}
                    # Preserve Type nodes for globals so we can check qualifiers like const.
                    self._global_decl_types: Dict[str, Type] = {}
                    self._enum_constants: Dict[str, int] = {}
                    self._global_arrays: Dict[str, tuple[str, int]] = {}
                # robustly across all declarator spellings.
                try:
                    if len(params_list) == 0 and decl.body is None:
                        self._function_param_types.setdefault(decl.name, None)
                    else:
                        def _canon_param_ty(t: Type) -> str:
                            return " ".join(str(t).strip().split())

                        typed_params = [p for p in params_list if getattr(p, "name", None) != "..."]
                        self._function_param_types.setdefault(
                            decl.name,
                            [_canon_param_ty(p.type) for p in typed_params],
                        )
                except Exception:
                    self._function_param_types.setdefault(decl.name, None)
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
                # Parser encodes arrays via Declaration.array_size, and multi-dim arrays
                # via Declaration.array_dims.
                try:
                    n = getattr(decl, "array_size", None)
                    dims = getattr(decl, "array_dims", None)
                    if dims:
                        # Preserve full dims (outer->inner). We'll use this in sizeof and
                        # later nested initializer lowering.
                        self._global_arrays[decl.name] = (str(getattr(decl.type, "base", "int")), [int(x) if x is not None else None for x in dims])
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
                except StopIteration:
                    pass
                except Exception:
                    pass

        for decl in ast.declarations:
            if isinstance(decl, FunctionDecl) and decl.body is not None:
                self._analyze_function(decl)
            elif isinstance(decl, Declaration) and decl.initializer is not None:
                # Reject classic const-dropping through pointer chains in global initializers.
                src_ty: Optional[Type] = None
                if isinstance(decl.initializer, Identifier):
                    src_ty = self._lookup_decl_type(decl.initializer.name)
                elif (
                    isinstance(decl.initializer, UnaryOp)
                    and decl.initializer.operator == "&"
                    and isinstance(decl.initializer.operand, Identifier)
                ):
                    src_ty = self._type_after_address_of_identifier(decl.initializer.operand.name)
                if self._reject_const_dropping_via_chain(decl.type, src_ty):
                    self.errors.append(
                        f"invalid conversion: initializer for '{decl.name}' drops const qualifiers in pointer chain"
                    )
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
            global_decl_types=dict(self._global_decl_types),
            global_linkage=dict(self._global_linkage),
            global_kinds=dict(self._global_kinds),
            function_sigs=dict(self._function_sigs),
            function_param_types=dict(self._function_param_types),
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
        if isinstance(expr, Cast):
            # C89: casts may appear inside constant expressions in a limited way.
            # For now, accept casts and evaluate the underlying expression.
            return self._eval_const_int(expr.expression)
        if isinstance(expr, SizeOf):
            # C89: sizeof(type-name) is an integer constant expression.
            if expr.operand is None and expr.type is not None:
                return int(_type_size(expr.type))
            # sizeof(expression) is not an ICE in C89.
            raise SemanticError("enum value must be an integer constant expression")
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
        mtypes: Dict[str, str] = {}

        def size_align(ty: Type) -> Tuple[int, int]:
            if ty.is_pointer:
                return 8, 8
            # Nested aggregates.
            if isinstance(ty.base, str) and (ty.base.startswith("struct ") or ty.base.startswith("union ")):
                key = ty.base.strip()
                lay = self._layouts.get(key)
                if lay is not None and getattr(lay, "size", 0):
                    try:
                        return int(lay.size), int(lay.align or 1)
                    except Exception:
                        return int(lay.size), 1
            if ty.base == "int":
                return 4, 4
            if ty.base == "char":
                return 1, 1
            # unknown types treated as 8-byte aligned scalar
            return 8, 8

        off = 0
        max_align = 1
        max_size = 0

        for m in members:
            sz, al = size_align(m.type)
            # This compiler doesn't currently model `double`/`long double`, but
            # on x86-64 we still ensure struct alignment is at least 8 when it
            # contains a pointer or an 8-byte member.
            if sz >= 8:
                al = max(al, 8)
            # Track member base type spelling for downstream (nested) init.
            try:
                if getattr(m.type, "is_pointer", False):
                    mtypes[m.name] = f"{m.type.base}*"
                else:
                    mtypes[m.name] = str(m.type.base)
            except Exception:
                mtypes[m.name] = str(getattr(m, "type", ""))
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

        return StructLayout(kind=kind, name=tag, size=size, align=max_align, member_offsets=offsets, member_sizes=sizes, member_types=mtypes)

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

    def _pointer_level_count(self, ty: Optional[Type]) -> int:
        if ty is None:
            return 0
        try:
            return int(getattr(ty, "pointer_level", 1 if getattr(ty, "is_pointer", False) else 0))
        except Exception:
            return 1 if getattr(ty, "is_pointer", False) else 0

    def _reject_const_dropping_via_chain(self, dst: Optional[Type], src: Optional[Type]) -> bool:
        """Subset of C qualifier rules:

        Reject converting `T **` to `const T **` (or equivalent via `&T*`) because it
        permits writing through a non-const intermediate pointer.

        This is intentionally narrow: it triggers only when both sides are at least
        double pointers and the destination introduces ultimate pointee const.
        """
        if dst is None or src is None:
            return False
        dl = self._pointer_level_count(dst)
        sl = self._pointer_level_count(src)

        def _ultimate_pointee_is_const(t: Type) -> bool:
            # Current representation: ultimate pointee const for `const T *...`
            # is tracked on the base qualifier.
            return bool(getattr(t, "is_const", False))

        # Only enforce the classic constraint when both are at least double pointers
        # and the destination introduces ultimate pointee const.
        if dl >= 2 and sl >= 2 and _ultimate_pointee_is_const(dst) and not _ultimate_pointee_is_const(src):
            return True
        return False

    def _type_after_address_of_identifier(self, ident_name: str) -> Optional[Type]:
        base = self._lookup_decl_type(ident_name)
        if base is None:
            return None
        if hasattr(base, "with_pointer_level"):
            return base.with_pointer_level(self._pointer_level_count(base) + 1)
        # Fallback for older Type shape
        return Type(
            base=getattr(base, "base", "int"),
            is_pointer=True,
            pointer_level=self._pointer_level_count(base) + 1,
            is_const=bool(getattr(base, "is_const", False)),
            is_volatile=bool(getattr(base, "is_volatile", False)),
            is_restrict=bool(getattr(base, "is_restrict", False)),
            is_unsigned=bool(getattr(base, "is_unsigned", False)),
            is_signed=bool(getattr(base, "is_signed", False)),
            line=getattr(base, "line", 1),
            column=getattr(base, "column", 1),
        )

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
                        # Reject classic const-dropping through pointer chains in initializers.
                        src_ty: Optional[Type] = None
                        if isinstance(item.initializer, Identifier):
                            src_ty = self._lookup_decl_type(item.initializer.name)
                        elif (
                            isinstance(item.initializer, UnaryOp)
                            and item.initializer.operator == "&"
                            and isinstance(item.initializer.operand, Identifier)
                        ):
                            src_ty = self._type_after_address_of_identifier(item.initializer.operand.name)
                        if self._reject_const_dropping_via_chain(item.type, src_ty):
                            self.errors.append(
                                f"invalid conversion: initializer for '{item.name}' drops const qualifiers in pointer chain"
                            )
                        self._analyze_expr(item.initializer)
                        # Extra: detect illegal pointer-chain qualifier conversions for
                        # common initializer forms where expression typing isn't implemented.
                        # Handles: `const int **cpp = pp;` and `const int **ppc = &pi;`.
                        try:
                            if isinstance(item.initializer, Identifier):
                                src_name = item.initializer.name
                                src_ty2 = self._lookup_decl_type(src_name)
                                if self._reject_const_dropping_via_chain(item.type, src_ty2):
                                    self.errors.append(
                                        f"invalid conversion: initializer for '{item.name}' drops const qualifiers in pointer chain"
                                    )
                            elif (
                                isinstance(item.initializer, UnaryOp)
                                and item.initializer.operator == "&"
                                and isinstance(item.initializer.operand, Identifier)
                            ):
                                src_ty2 = self._type_after_address_of_identifier(item.initializer.operand.name)
                                if self._reject_const_dropping_via_chain(item.type, src_ty2):
                                    self.errors.append(
                                        f"invalid conversion: initializer for '{item.name}' drops const qualifiers in pointer chain"
                                    )
                        except Exception:
                            pass
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
                        src_ty: Optional[Type] = None
                        if isinstance(item.initializer, Identifier):
                            src_ty = self._lookup_decl_type(item.initializer.name)
                        elif (
                            isinstance(item.initializer, UnaryOp)
                            and item.initializer.operator == "&"
                            and isinstance(item.initializer.operand, Identifier)
                        ):
                            src_ty = self._type_after_address_of_identifier(item.initializer.operand.name)
                        if self._reject_const_dropping_via_chain(item.type, src_ty):
                            self.errors.append(
                                f"invalid conversion: initializer for '{item.name}' drops const qualifiers in pointer chain"
                            )
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
                    src_ty: Optional[Type] = None
                    if isinstance(stmt.init.initializer, Identifier):
                        src_ty = self._lookup_decl_type(stmt.init.initializer.name)
                    elif (
                        isinstance(stmt.init.initializer, UnaryOp)
                        and stmt.init.initializer.operator == "&"
                        and isinstance(stmt.init.initializer.operand, Identifier)
                    ):
                        src_ty = self._type_after_address_of_identifier(stmt.init.initializer.operand.name)
                    if self._reject_const_dropping_via_chain(stmt.init.type, src_ty):
                        self.errors.append(
                            f"invalid conversion: initializer for '{stmt.init.name}' drops const qualifiers in pointer chain"
                        )
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
        # Best-effort type propagation for later stages (IR/codegen).
        # This is not a full C89 typing engine yet, but it gives us a stable
        # place to start wiring type info into expressions.
        try:
            if not hasattr(expr, "type"):
                setattr(expr, "type", None)
        except Exception:
            pass

        if isinstance(expr, (IntLiteral, StringLiteral, CharLiteral)):
            try:
                if isinstance(expr, IntLiteral):
                    expr.type = Type(base="int", line=expr.line, column=expr.column)
                elif isinstance(expr, CharLiteral):
                    expr.type = Type(base="int", line=expr.line, column=expr.column)
                elif isinstance(expr, StringLiteral):
                    expr.type = Type(base="char", is_pointer=True, pointer_level=1, line=expr.line, column=expr.column)
                    expr.type._normalize_pointer_state()
            except Exception:
                pass
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
            try:
                ty = self._lookup_decl_type(expr.name)
                if ty is not None:
                    expr.type = ty
            except Exception:
                pass
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
                # C semantics: `const int *p` is an *assignable* pointer object.
                # Only the referenced object is const. We only reject
                # `T const p` (non-pointer const object) and `T * const p`
                # (const-qualified pointer object).
                if ty is not None and not getattr(ty, "is_pointer", False) and getattr(ty, "is_const", False):
                    self.errors.append(f"Assignment to const-qualified variable '{expr.target.name}'")

                # Also reject assignment to a const-qualified pointer object: `T *const p; p = ...;`
                # This is distinct from `const T *p` (pointer-to-const), which remains assignable.
                if getattr(ty, "is_pointer", False):
                    # Treat as pointer-object const only when the *outermost pointer*
                    # level has const (i.e. `T * const p`). Base-type const
                    # (i.e. `const T *p`) must remain assignable.
                    try:
                        is_ptr_obj_const = bool(
                            getattr(ty, "pointer_level", 0) > 0
                            and isinstance(getattr(ty, "pointer_quals", None), list)
                            and len(ty.pointer_quals) > 0
                            and ("const" in ty.pointer_quals[0])
                        )
                    except Exception:
                        is_ptr_obj_const = False

                    if is_ptr_obj_const:
                        self.errors.append(f"Assignment to const-qualified pointer variable '{expr.target.name}'")

            def _expr_is_nonmodifiable_lvalue(e: Expression) -> bool:
                """Return True if e is a non-modifiable lvalue (const-qualified).

                Subset implemented:
                - identifier of const-qualified object
                - array element where the array element type is const-qualified
                  (e.g. `const int a[2]; a[0] = 1;`)
                """

                if isinstance(e, Identifier):
                    ty2 = self._lookup_decl_type(e.name)
                    # A pointer-to-const variable is still a modifiable lvalue;
                    # const applies to what it points at.
                    return bool(
                        ty2 is not None
                        and (not getattr(ty2, "is_pointer", False))
                        and getattr(ty2, "is_const", False)
                    )

                if isinstance(e, ArrayAccess) and isinstance(e.array, Identifier):
                    aty = self._lookup_decl_type(e.array.name)
                    # Parser encodes arrays via Declaration.array_size/array_dims; element type
                    # qualifiers are carried on the base Type node.
                    return bool(aty is not None and getattr(aty, "is_const", False))

                return False

            # Stricter rule: reject assignment to const-qualified subobjects
            # like `a[0]` when `a` is `const T[]`.
            if _expr_is_nonmodifiable_lvalue(expr.target):
                self.errors.append("Assignment to non-modifiable lvalue")

            # Feature B (subset): reject writes through pointers-to-const.
            # Detect `*p = ...` where `p` was declared as `const T*`.
            if isinstance(expr.target, UnaryOp) and expr.target.operator == "*":
                # Best-effort: only handle deref of a plain identifier.
                # (Full lvalue type propagation is deferred.)
                if isinstance(expr.target.operand, Identifier):
                    p_name = expr.target.operand.name
                    p_ty = self._lookup_decl_type(p_name)
                    # Current representation: pointee const for `const T *p`
                    # is stored on Type.is_const (even for pointers).
                    if p_ty is not None and getattr(p_ty, "is_pointer", False) and getattr(p_ty, "is_const", False):
                        self.errors.append(f"Assignment through pointer to const is not allowed: '*{p_name}'")

            # Pointer assignment from integer (subset): allow only 0 as a null
            # pointer constant in plain '=' assignment.
            # Reject `T* p; p = 1;` unless explicitly cast.
            try:
                if (
                    getattr(expr, "operator", "=") == "="
                    and isinstance(expr.target, Identifier)
                    and not isinstance(expr.value, Cast)
                ):
                    dst_ty = self._lookup_decl_type(expr.target.name)
                    if dst_ty is not None and getattr(dst_ty, "is_pointer", False):
                        if isinstance(expr.value, IntLiteral) and int(expr.value.value) != 0:
                            self.errors.append(
                                "invalid conversion: assignment from non-zero integer constant to pointer requires a cast"
                            )
            except Exception:
                pass

            def _deref_depth(e: Expression) -> tuple[int, Optional[str]]:
                d = 0
                while isinstance(e, UnaryOp) and e.operator == "*":
                    d += 1
                    e = e.operand
                if isinstance(e, Identifier):
                    return d, e.name
                return d, None

            def _outermost_pointee_is_const(ty: Optional[Type]) -> bool:
                if ty is None:
                    return False
                # Current representation: ultimate pointee const for `const T *...`
                # is stored on Type.is_const.
                return bool(getattr(ty, "is_const", False))

            def _pointer_level_count(ty: Optional[Type]) -> int:
                if ty is None:
                    return 0
                try:
                    return int(getattr(ty, "pointer_level", 1 if getattr(ty, "is_pointer", False) else 0))
                except Exception:
                    return 1 if getattr(ty, "is_pointer", False) else 0

            def _reject_const_dropping(dst: Optional[Type], src: Optional[Type]) -> bool:
                if dst is None or src is None:
                    return False
                dl = _pointer_level_count(dst)
                sl = _pointer_level_count(src)
                if dl >= 2 and sl >= 2 and getattr(dst, "is_const", False) and not getattr(src, "is_const", False):
                    return True
                return False

            # Multi-level write rejection: `**pp = ...` where ultimate pointee is const.
            d, name = _deref_depth(expr.target)
            if d >= 2 and name is not None:
                ty = self._lookup_decl_type(name)
                if ty is not None and _pointer_level_count(ty) >= d and _outermost_pointee_is_const(ty):
                    self.errors.append(
                        f"Assignment through pointer to const is not allowed: '{'*' * d}{name}'"
                    )

            # Multi-level conversion constraint (subset): reject const-dropping via pointer chains.
            # - const int **cpp = pp; where pp is int **
            # - const int **ppc = &pi; where pi is int *
            if isinstance(expr.target, Identifier):
                dst_ty = self._lookup_decl_type(expr.target.name)
                src_ty: Optional[Type] = None
                if isinstance(expr.value, Identifier):
                    src_ty = self._lookup_decl_type(expr.value.name)
                    # If RHS is a function identifier used in expression context,
                    # it decays to a function pointer. Use recorded function
                    # signature info (arity) for compatibility checks.
                    if src_ty is None and expr.value.name in getattr(self, "_function_sigs", {}):
                        try:
                            _ret, _pc, _is_var = self._function_sigs[expr.value.name]
                            src_ty = Type(base=f"{_ret} (*)()", is_pointer=True, pointer_level=1, line=expr.value.line, column=expr.value.column)
                            src_ty._normalize_pointer_state()
                            src_ty.fn_param_count = _pc
                        except Exception:
                            src_ty = None
                elif isinstance(expr.value, UnaryOp) and expr.value.operator == "&" and isinstance(expr.value.operand, Identifier):
                    src_ty = self._type_after_address_of_identifier(expr.value.operand.name)
                if self._reject_const_dropping_via_chain(dst_ty, src_ty) or _reject_const_dropping(dst_ty, src_ty):
                    self.errors.append(
                        f"invalid conversion: assignment to '{expr.target.name}' drops const qualifiers in pointer chain"
                    )

                # Pointer from integer (subset): allow only null pointer constants.
                # Reject `T* p; p = 1;` (no cast) but allow `p = 0;`.
                # IMPORTANT: do not reject pointer arithmetic expressions like `p += 1`
                # which are represented as an Assignment with a BinaryOp RHS.
                # NOTE: This is a narrow rule intended to catch direct assignments like
                # `p = 1;` while not breaking pointer arithmetic (`p += 1`).
                try:
                    if dst_ty is not None and getattr(dst_ty, "is_pointer", False) and getattr(expr, "operator", "=") == "=":
                        if not isinstance(expr.value, Cast):
                            # Skip if RHS is already pointer-typed.
                            rhs_ty = self._infer_type(expr.value)
                            if rhs_ty is not None and getattr(rhs_ty, "is_pointer", False):
                                raise StopIteration()
                            # Only reject literal integer constants that are non-zero.
                            if isinstance(expr.value, IntLiteral) and int(expr.value.value) != 0:
                                self.errors.append(
                                    "invalid conversion: assignment from non-zero integer constant to pointer requires a cast"
                                )
                except StopIteration:
                    pass
                except Exception:
                    pass

                # Pointer compatibility (subset): reject incompatible object pointer assignment
                # without an explicit cast, except for void* which is compatible with any
                # object pointer.
                try:
                    if (
                        dst_ty is not None
                        and src_ty is not None
                        and getattr(dst_ty, "is_pointer", False)
                        and getattr(src_ty, "is_pointer", False)
                    ):
                        dst_base = str(getattr(dst_ty, "base", ""))
                        src_base = str(getattr(src_ty, "base", ""))
                        # Function pointer compatibility (subset): when both sides are
                        # pointers to functions (parser encodes base like `int (*)()`),
                        # enforce arity if available.
                        if "(*)" in dst_base and "(*)" in src_base:
                            d_arity = getattr(dst_ty, "fn_param_count", None)
                            s_arity = getattr(src_ty, "fn_param_count", None)
                            if d_arity is not None and s_arity is not None and d_arity != s_arity:
                                self.errors.append(
                                    f"incompatible function pointer types in assignment: arity {d_arity} from arity {s_arity}"
                                )
                            # Do not apply object-pointer base checks to function pointers.
                            raise StopIteration()
                        # void* <-> T* allowed (object pointers subset)
                        if dst_base != "void" and src_base != "void" and dst_base != src_base:
                            self.errors.append(
                                f"incompatible pointer types in assignment: '{dst_base}*' from '{src_base}*'"
                            )
                except StopIteration:
                    pass
                except Exception:
                    pass

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

            # C89 default argument promotions apply for calls through a
            # non-prototype function type (e.g. `int f();`).
            # Minimal subset: integer promotions only (char/short -> int).
            # We rewrite the AST to explicit Cast nodes so later IR/codegen
            # sees the promoted value.
            try:
                if self._is_non_prototype_call(expr):
                    expr.arguments = [self._apply_default_argument_promotions(a) for a in expr.arguments]
            except Exception:
                # Best-effort: never crash semantic analysis due to promotion logic.
                pass

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

    def _is_non_prototype_call(self, call: FunctionCall) -> bool:
        if not isinstance(call.function, Identifier):
            return False
        name = call.function.name
        sig = getattr(self, "_function_sigs", {}).get(name)
        # Convention used elsewhere: param_count=None indicates an old-style
        # (non-prototype) declaration `T f();`.
        return bool(sig is not None and sig.get("param_count") is None)

    def _apply_default_argument_promotions(self, arg: Expression) -> Expression:
        # Only promote plain identifiers with known declared types.
        # (This keeps the subset small and avoids needing full expression typing.)
        from pycc.ast_nodes import Cast as _Cast

        if not isinstance(arg, Identifier):
            return arg
        ty = self._lookup_decl_type(arg.name)
        if ty is None or getattr(ty, "is_pointer", False):
            return arg
        base = str(getattr(ty, "base", ""))
        if base in {"char", "signed char", "unsigned char", "short", "short int", "signed short", "signed short int", "unsigned short", "unsigned short int"}:
            to_ty = Type(base="int", line=arg.line, column=arg.column)
            return _Cast(line=arg.line, column=arg.column, type=to_ty, expression=arg)
        return arg

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
