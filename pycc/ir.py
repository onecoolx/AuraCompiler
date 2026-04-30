"""pycc.ir — Intermediate Representation for AuraCompiler.

TAC-like instruction list with float-aware ops (fmov/fadd/fsub/fmul/fdiv/fcmp)
and type conversion instructions (i2f/i2d/f2i/d2i/f2d/d2f).

IR is organized as a list of `IRInstruction` plus a few container records:

- `func_begin` / `func_end`
- `label`, `jmp`, `jz`
- `mov`, `binop`, `call`, `ret`

Operands are simple strings (temporaries like %t0, locals like @x, immediates
like $5, and labels like .L1). The code generator will interpret them.
"""

from __future__ import annotations

import struct as _struct
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Union, Any

from pycc.types import (
    CType, TypedSymbolTable, ctype_to_ir_type, ast_type_to_ctype_resolved,
    TypeKind, IntegerType, FloatType, PointerType,
    ArrayType as CArrayType, StructType as CStructType,
    type_sizeof, _str_to_ctype, resolve_typedefs,
)


from pycc.ast_nodes import (
    Program,
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
    ReturnStmt,
    BreakStmt,
    ContinueStmt,
    GotoStmt,
    LabelStmt,
    Identifier,
    IntLiteral,
    FloatLiteral,
    StringLiteral,
    BinaryOp,
    UnaryOp,
    ArrayType,
    Assignment,
    FunctionCall,
    ArrayAccess,
    MemberAccess,
    PointerMemberAccess,
    TernaryOp,
    CommaOp,
    SizeOf,
    Cast,
    Initializer,
    Designator,
    CharLiteral,
    Statement,
    Expression,
)


class IRGenError(Exception):
    pass


def _eval_const_int_expr(expr: Expression, enum_constants: dict = None) -> int:
    """Unified integer constant expression (ICE) evaluator (C89).

    Supports: integer/char literals, sizeof(type-name), enum constants (via
    attached value or enum_constants dict), unary +/-/~/!, all binary
    arithmetic/bitwise/relational/logical operators, ternary, comma, and casts.
    """

    if isinstance(expr, IntLiteral):
        return int(expr.value)
    if isinstance(expr, CharLiteral):
        return ord(expr.value)
    if isinstance(expr, UnaryOp) and expr.operator in {"+", "-", "~", "!"}:
        v = _eval_const_int_expr(expr.operand, enum_constants)
        if expr.operator == "+":
            return v
        if expr.operator == "-":
            return -v
        if expr.operator == "!":
            return 0 if v != 0 else 1
        return ~v
    _binops = {"+", "-", "*", "/", "%", "|", "&", "^", "<<", ">>",
               "<", ">", "<=", ">=", "==", "!=", "&&", "||"}
    if isinstance(expr, BinaryOp) and expr.operator in _binops:
        l = _eval_const_int_expr(expr.left, enum_constants)
        r = _eval_const_int_expr(expr.right, enum_constants)
        op = expr.operator
        if op == "+": return l + r
        if op == "-": return l - r
        if op == "*": return l * r
        if op == "/": return int(l / r) if r != 0 else 0
        if op == "%": return l % r if r != 0 else 0
        if op == "|": return l | r
        if op == "&": return l & r
        if op == "^": return l ^ r
        if op == "<<": return l << r
        if op == ">>": return l >> r
        if op == "<": return 1 if l < r else 0
        if op == ">": return 1 if l > r else 0
        if op == "<=": return 1 if l <= r else 0
        if op == ">=": return 1 if l >= r else 0
        if op == "==": return 1 if l == r else 0
        if op == "!=": return 1 if l != r else 0
        if op == "&&": return 1 if (l != 0 and r != 0) else 0
        if op == "||": return 1 if (l != 0 or r != 0) else 0
    if isinstance(expr, CommaOp):
        _eval_const_int_expr(expr.left, enum_constants)
        return _eval_const_int_expr(expr.right, enum_constants)
    if isinstance(expr, TernaryOp):
        cond = _eval_const_int_expr(expr.condition, enum_constants)
        if cond != 0:
            return _eval_const_int_expr(expr.true_expr, enum_constants)
        return _eval_const_int_expr(expr.false_expr, enum_constants)
    # Cast: evaluate inner expression
    if isinstance(expr, Cast):
        return _eval_const_int_expr(expr.expression, enum_constants)
    # sizeof(type-name)
    from pycc.ast_nodes import SizeOf
    if isinstance(expr, SizeOf):
        if expr.type is not None:
            return int(_type_size(expr.type))
        raise IRGenError("sizeof(expression) is not an integer constant expression")
    # Identifier: check attached enum value or enum_constants dict
    if isinstance(expr, Identifier):
        v = getattr(expr, '_enum_value', None)
        if v is not None:
            return int(v)
        if enum_constants and expr.name in enum_constants:
            return int(enum_constants[expr.name])

    raise IRGenError("not an integer constant expression")


# Module-level default TargetInfo for functions that lack a sema_ctx.
from pycc.target import TargetInfo as _TargetInfo, _normalize
_DEFAULT_TARGET = _TargetInfo.lp64()


def _get_target(sema_ctx: object = None) -> '_TargetInfo':
    """Return the TargetInfo from sema_ctx, falling back to LP64 default."""
    if sema_ctx is not None:
        t = getattr(sema_ctx, "target", None)
        if t is not None:
            return t
    return _DEFAULT_TARGET


def _type_size(ty: Optional[object], sema_ctx: object = None) -> int:
    """Best-effort sizeof for the current project stage."""

    if ty is None:
        return 8
    target = _get_target(sema_ctx)
    if isinstance(ty, str):
        b = " ".join(ty.strip().split())
        if "*" in b:
            return target.pointer_size
        # Resolve typedef to underlying type.
        if sema_ctx is not None and not b.startswith("struct ") and not b.startswith("union ") and not b.startswith("enum "):
            td = getattr(sema_ctx, "typedefs", {}).get(b)
            if td is not None:
                return _type_size(td, sema_ctx)
        if b.startswith("struct ") or b.startswith("union "):
            if sema_ctx is not None:
                layouts = getattr(sema_ctx, "layouts", None) or getattr(sema_ctx, "_layouts", {})
                layout = layouts.get(b)
                if layout is not None and int(getattr(layout, "size", 0)) > 0:
                    return int(getattr(layout, "size", 0))
            raise IRGenError(f"invalid application of sizeof to incomplete type '{b}'")
        return target.sizeof(b)

    base = getattr(ty, "base", None)
    if isinstance(base, str):
        if getattr(ty, "is_pointer", False):
            return target.pointer_size
        b = " ".join(base.strip().split())
        # Resolve typedef to underlying type.
        if sema_ctx is not None and not b.startswith("struct ") and not b.startswith("union ") and not b.startswith("enum "):
            td = getattr(sema_ctx, "typedefs", {}).get(b)
            if td is not None:
                return _type_size(td, sema_ctx)
        if "(" in b and ")" in b and "*" not in b:
            raise IRGenError("invalid application of sizeof to function type")
        if b.startswith("struct ") or b.startswith("union "):
            if sema_ctx is not None:
                layouts = getattr(sema_ctx, "layouts", None) or getattr(sema_ctx, "_layouts", {})
                layout = layouts.get(b)
                if layout is not None and int(getattr(layout, "size", 0)) > 0:
                    return int(getattr(layout, "size", 0))
            raise IRGenError(f"invalid application of sizeof to incomplete type '{b}'")
        return target.sizeof(b)
    # fallback
    return 8


def _type_align(ty: Optional[object]) -> int:
    """Best-effort alignment for the current project stage (x86-64 SysV).

    This is used for padding when packing constant initializer blobs for
    structs/unions.
    """

    if ty is None:
        return 8
    target = _DEFAULT_TARGET
    if isinstance(ty, str):
        b = ty.strip()
        if "*" in b:
            return target.pointer_size
        return target.alignof(b)

    base = getattr(ty, "base", None)
    if isinstance(base, str):
        if getattr(ty, "is_pointer", False):
            return target.pointer_size
        b = base.strip()
        return target.alignof(b)
    return 8


def _type_size_bytes(sema_ctx: object, ty: Optional[object]) -> int:
    """Best-effort size (bytes) for constant-initializer packing."""
    if ty is None:
        return 0
    target = _get_target(sema_ctx)
    if isinstance(ty, str):
        b = ty.strip()
        if b.startswith("struct ") or b.startswith("union "):
            layout = getattr(sema_ctx, "layouts", {}).get(b)
            return int(getattr(layout, "size", 0) or 0) if layout is not None else 0
        if "*" in b:
            return target.pointer_size
        if "long long" in b:
            return 8
        # Use TargetInfo for known scalar types; return 0 for unknowns.
        n = _normalize(b)
        if n.startswith("enum "):
            return target.sizeof(n)
        if n in target._sizes:
            return target._sizes[n]
        return 0

    # Type node
    kind = getattr(ty, "kind", None)
    if kind in ("struct", "union"):
        layout = getattr(sema_ctx, "layouts", {}).get(str(ty))
        return int(getattr(layout, "size", 0) or 0) if layout is not None else 0
    if kind == "pointer" or getattr(ty, "is_pointer", False):
        return target.pointer_size
    if kind == "array":
        base_sz = _type_size_bytes(sema_ctx, getattr(ty, "base", None))
        n = getattr(ty, "size", None)
        return base_sz * int(n) if n is not None else 0

    base = getattr(ty, "base", None)
    return _type_size_bytes(sema_ctx, base if base is not None else str(ty))


@dataclass
class IRInstruction:
    op: str
    result: Optional[str] = None
    operand1: Optional[str] = None
    operand2: Optional[str] = None
    label: Optional[str] = None
    args: Optional[List[str]] = None
    meta: Optional[dict] = None
    # CType for the result operand (optional).
    result_type: Optional[CType] = None

    def __post_init__(self) -> None:
        if self.args is None:
            self.args = []
        if self.meta is None:
            self.meta = {}


class IRGenerator:
    """Generates intermediate representation (3-Address Code)"""
    
    def __init__(self):
        self.instructions: List[IRInstruction] = []
        self.temp_counter = 0
        self.label_counter = 0
        self._break_stack: List[str] = []
        self._continue_stack: List[str] = []
        self._sema_ctx = None
        self._scope_stack: List[Dict[str, str]] = []  # name -> IR symbol mapping
        self._shadow_counter = 0
        self._sym_table: Optional[TypedSymbolTable] = None
        self._target = None  # resolved lazily from sema_ctx in generate()

    def _sizeof(self, ty: object) -> int:
        """Return sizeof(ty) using the module-level _type_size with sema_ctx.

        All IRGenerator code should call self._sizeof() instead of the
        module-level _type_size() directly.  This ensures the semantic
        context (struct/union layouts, typedefs) is always available and
        eliminates the class of bugs where a caller forgets to pass
        sema_ctx.
        """
        return _type_size(ty, self._sema_ctx)
    
    def generate(self, ast: Program) -> List[IRInstruction]:
        """Generate IR from AST"""
        self.instructions = []
        self.temp_counter = 0
        self.label_counter = 0
        self._break_stack = []
        self._continue_stack = []
        self._local_array_dims = {}
        # Per-temp/symbol pointer arithmetic step override (bytes).
        # Used for pointer-to-row decay where (p+1) advances by sizeof(row).
        self._ptr_step_bytes: dict[str, int] = {}
        self._enum_constants: dict[str, int] = {}
        self._local_arrays: set[str] = set()
        if self._sema_ctx is not None:
            self._sym_table = TypedSymbolTable(self._sema_ctx)
        else:
            self._sym_table = None
        # Resolve TargetInfo from sema_ctx (with fallback to LP64 default)
        from pycc.target import TargetInfo
        if self._sema_ctx is not None and hasattr(self._sema_ctx, 'target'):
            self._target = self._sema_ctx.target
        else:
            self._target = TargetInfo.lp64()
        for decl in ast.declarations:
            from pycc.ast_nodes import EnumDecl
            if isinstance(decl, EnumDecl):
                cur = -1
                for name, val_expr in (decl.enumerators or []):
                    if val_expr is None:
                        cur += 1
                    else:
                        # Reuse the semantics evaluator if available later; for now
                        # support simple integer literals only.
                        if hasattr(val_expr, "value"):
                            cur = int(getattr(val_expr, "value"))
                        else:
                            cur = cur + 1
                    self._enum_constants[name] = cur

        for decl in ast.declarations:
            if isinstance(decl, FunctionDecl) and decl.body is not None:
                self._gen_function(decl)
            elif isinstance(decl, Declaration):
                # Global decl/def.
                sc = getattr(decl, "storage_class", None)
                if getattr(decl, "initializer", None) is None:
                    self.instructions.append(
                        IRInstruction(
                            op="gdecl",
                            result=f"@{decl.name}",
                            operand1=decl.type.base,
                            # Distinguish `extern int g;` from a tentative
                            # definition `int g;`.
                            # C89: a file-scope declaration without initializer
                            # and without `extern` is a tentative definition.
                            label="extern" if sc == "extern" else "tentative",
                        )
                    )
                else:
                    init = getattr(decl, "initializer")
                    # Subset: allow global aggregate initializers for fixed-size arrays
                    # and structs/unions, provided the initializer is constant.
                    blob = self._const_initializer_blob(decl)
                    if blob is not None:
                        self.instructions.append(
                            IRInstruction(
                                op="gdef_blob",
                                result=f"@{decl.name}",
                                operand1=decl.type.base,
                                operand2=blob,
                                label=sc,
                            )
                        )
                    else:
                        imm = self._const_initializer_imm(init)
                        ptr = self._const_initializer_ptr(init)
                        # Float global initializer
                        if isinstance(init, FloatLiteral):
                            suffix = getattr(init, 'suffix', '')
                            if suffix in ('l', 'L'):
                                fp_type = "long double"
                            elif suffix in ('f', 'F'):
                                fp_type = "float"
                            else:
                                fp_type = "double"
                            self.instructions.append(
                                IRInstruction(
                                    op="gdef_float",
                                    result=f"@{decl.name}",
                                    operand1=str(init.value),
                                    label=sc,
                                    meta={"fp_type": fp_type},
                                )
                            )
                            continue
                        elif imm is None and ptr is None:
                            # Try struct/union member-by-member initialization.
                            # This handles structs with function pointer members,
                            # symbol references, and mixed types that blob can't encode.
                            struct_init = self._try_struct_member_init(decl, sc)
                            if struct_init:
                                continue
                            # Try: array of string-literal pointers
                            # e.g. char *arr[] = {"str1", "str2"};
                            # or   void (*fn_arr[])(T*) = {f, g};  (function pointer array)
                            if isinstance(init, Initializer) and getattr(decl.type, "is_pointer", False):
                                inits_list = self._const_initializer_list(init)
                                if inits_list and all(isinstance(e, StringLiteral) for e in inits_list):
                                    # Emit pointer array with string literal references.
                                    # Codegen will intern each string and emit .quad <label>.
                                    str_values = [e.value for e in inits_list]
                                    self.instructions.append(
                                        IRInstruction(
                                            op="gdef_ptr_array",
                                            result=f"@{decl.name}",
                                            operand1=decl.type.base,
                                            label=sc,
                                            meta={"strings": str_values},
                                        )
                                    )
                                    continue
                                # Function pointer array: emit each name as a symbol ref
                                if inits_list and all(isinstance(e, Identifier) for e in inits_list):
                                    sym_labels = [e.name for e in inits_list]
                                    self.instructions.append(
                                        IRInstruction(
                                            op="gdef_ptr_array",
                                            result=f"@{decl.name}",
                                            operand1=decl.type.base,
                                            label=sc,
                                            meta={"symbols": sym_labels},
                                        )
                                    )
                                    continue
                            raise IRGenError(
                                f"unsupported global initializer for {decl.name}: only integer/char constants and string-literal pointers supported"
                            )

                        # Special-case: `char s[] = "...";` at file scope is an
                        # aggregate initializer for a character array, not a
                        # pointer initializer.
                        # The parser encodes unsized arrays as `array_size=None`.
                        if (
                            imm is None
                            and isinstance(ptr, str)
                            and ptr.startswith("=str:")
                            and getattr(decl, "array_size", None) is None
                            and getattr(getattr(decl, "type", None), "base", None) in {"char", "unsigned char"}
                            and not getattr(getattr(decl, "type", None), "is_pointer", False)
                        ):
                            s = ptr[len("=str:") :]
                            # include trailing NUL
                            bs = [ord(c) & 0xFF for c in s] + [0]
                            blob2 = "blob:" + "".join(f"{b:02x}" for b in bs)
                            self.instructions.append(
                                IRInstruction(
                                    op="gdef_blob",
                                    result=f"@{decl.name}",
                                    operand1=decl.type.base,
                                    operand2=blob2,
                                    label=sc,
                                )
                            )
                            continue

                        self.instructions.append(
                            IRInstruction(
                                op="gdef",
                                result=f"@{decl.name}",
                                operand1=decl.type.base,
                                operand2=imm if imm is not None else ptr,
                                label=sc,
                            )
                        )
        return self.instructions

    def _canon_int_type(self, ty: object | None) -> str:
        """Canonicalize a best-effort integer type string.

        This project uses stringly-typed ints in IR/codegen. Normalizing to a
        small set reduces mismatches like "short int" vs "short".
        """

        if ty is None:
            return ""
        if isinstance(ty, str):
            raw = ty.strip()
        else:
            try:
                raw = str(ty).strip()
            except Exception:
                return ""

        # Struct/union names are case-sensitive (layout keys preserve
        # original case).  Return them without lowercasing.
        if raw.startswith("struct ") or raw.startswith("union "):
            return raw

        s = " ".join(raw.lower().split())

        # normalize common spellings
        if s in {"short int", "short"}:
            return "short"
        if s in {"signed short", "signed short int"}:
            return "short"
        if s in {"unsigned short", "unsigned short int"}:
            return "unsigned short"
        if s in {"int", "signed int"}:
            return "int"
        if s in {"unsigned int"}:
            return "unsigned int"
        if s in {"long", "long int", "signed long", "signed long int"}:
            return "long"
        if s in {"unsigned long", "unsigned long int"}:
            return "unsigned long"
        if s in {"char", "signed char"}:
            return "char"
        if s in {"unsigned char"}:
            return "unsigned char"

        return s

    def _const_initializer_blob(self, decl: Declaration) -> Optional[str]:
        """Return a blob initializer string for a global aggregate, or None.

        Encoding is: "blob:<hex bytes>".
        Subset:
        - fixed-size int/char arrays with brace init (int/char consts only)
        - fixed-size char arrays with string literal init
        - struct/union with brace init (member-order), scalar consts only
        - array of structs with brace init (nested brace lists), scalar consts only
        """

        init = getattr(decl, "initializer", None)
        if init is None:
            return None

        # decl.type is usually a Type (scalars) or an ArrayType (arrays)
        base = getattr(decl.type, "base", None)
        if base is None and isinstance(getattr(decl, "type", None), str):
            # Some internal helpers / tests may pass a raw type string.
            base = decl.type
        if isinstance(decl.type, ArrayType):
            base = str(getattr(decl.type.element_type, "base", base))

        # Resolve typedef to underlying type once at the entry point.
        # This ensures all downstream checks (_is_struct_or_union_type,
        # layouts.get, _scalar_pack_info) work with the real type name
        # regardless of how many typedef layers wrap it.
        if isinstance(base, str) and self._sema_ctx is not None:
            resolved = self._resolve_elem_type(base.strip())
            if resolved != base.strip():
                base = resolved
        # Arrays: represented by decl.array_size (parser doesn't always wrap type).
        # Also handle unsized arrays (`T a[] = {...}`) by inferring element count
        # from the initializer list.
        is_array_decl = (
            isinstance(decl.type, ArrayType)
            or getattr(decl, "array_size", None) is not None
            or (
                # Parser encodes `T a[]` as base type T with array_size=None
                # and array_dims=[None]. Only treat it as an array when
                # array_dims is present (avoid misclassifying structs).
                getattr(decl, "array_size", None) is None
                and getattr(decl, "array_dims", None) is not None
                and isinstance(init, Initializer)
                and (
                    # Only treat a struct/union as an unsized array if the
                    # initializer is nested (i.e., looks like {{...},{...}}).
                    (self._is_struct_or_union_type(base) and any(isinstance(x, Initializer) for x in (self._const_initializer_list(init) or [])))
                    or self._scalar_pack_info(self._resolve_elem_type(str(base).strip())) is not None
                )
            )
        )
        if is_array_decl:
            # Handle `T a[N] = {...}` and also `T a[] = {...}` (size inferred
            # from initializer list length) for supported element types.
            n0 = getattr(decl, "array_size", None)
            if n0 is None:
                inits0 = self._const_initializer_list(init)
                if inits0 is None:
                    return None
                n = len(inits0)
            else:
                n = int(n0)

            # Check for designated array initializers at global scope.
            if isinstance(init, Initializer) and any(d is not None for d, _v in (init.elements or [])):
                return self._const_designated_array_blob(decl, init, n)
            if isinstance(decl.type, ArrayType):
                elem_ty = getattr(decl.type, "element_type", None)
                elem_base = str(getattr(elem_ty, "base", base)).strip()
            else:
                elem_base = str(base).strip() if base is not None else ""
            # Unsized array-of-struct declared like `struct S a[] = {...}` is
            # parsed as a plain Type("struct S") with array_size=None.
            # In that case, the element type is the struct itself.
            if self._is_struct_or_union_type(base) and any(isinstance(x, Initializer) for x in (self._const_initializer_list(init) or [])):
                elem_base = str(base).strip()
            # Resolve typedef to underlying type for matching.
            elem_base = self._resolve_elem_type(elem_base)

            # --- Unified: flatten nested initializers and compute total element count ---
            inits_raw = self._const_initializer_list(init)
            if inits_raw is None:
                return None

            def _flatten_inits(items: list) -> list:
                """Recursively flatten nested Initializer lists."""
                out = []
                for e in items:
                    if isinstance(e, Initializer):
                        sub = self._const_initializer_list(e)
                        if sub is not None:
                            out.extend(_flatten_inits(sub))
                        else:
                            out.append(e)
                    else:
                        out.append(e)
                return out

            total = n
            ad = getattr(decl, "array_dims", None)
            if isinstance(ad, list) and len(ad) >= 2:
                known_product = 1
                has_none = False
                for dim in ad:
                    if isinstance(dim, int) and dim > 0:
                        known_product *= dim
                    else:
                        has_none = True
                if has_none:
                    flat_preview = _flatten_inits(inits_raw)
                    total = max(len(flat_preview), known_product)
                else:
                    total = known_product

            # --- Special case: char array from string literal (not flattened) ---
            if elem_base in {"char", "unsigned char", "signed char"}:
                if len(inits_raw) == 1 and isinstance(inits_raw[0], StringLiteral):
                    s = inits_raw[0].value
                    bytes_vals = [ord(c) for c in s]
                    if len(bytes_vals) + 1 > n:
                        raise IRGenError(
                            f"string literal initializer too long for array '{decl.name}'"
                        )
                    bytes_vals.append(0)
                    if len(bytes_vals) < n:
                        bytes_vals = bytes_vals + [0] * (n - len(bytes_vals))
                    return "blob:" + "".join(f"{b & 0xFF:02x}" for b in bytes_vals)

            # --- Unified scalar array blob: table-driven packing ---
            pack_info = self._scalar_pack_info(elem_base)
            if pack_info is not None:
                elem_sz, pack_fn = pack_info
                flat = _flatten_inits(inits_raw)
                if len(flat) > total:
                    raise IRGenError(f"excess elements in initializer for array '{decl.name}'")
                blob = bytearray()
                for e in flat[:total]:
                    packed = pack_fn(e)
                    if packed is None:
                        return None
                    blob.extend(packed)
                blob += b'\x00' * (elem_sz * (total - len(flat)))
                return "blob:" + blob.hex()

            # Array of struct/union (subset): nested brace lists where each element
            # is a constant aggregate initializer.
            if self._is_struct_or_union_type(elem_base):
                inits = self._const_initializer_list(init)
                if inits is None:
                    return None
                if self._sema_ctx is None:
                    return None
                layout = getattr(self._sema_ctx, "layouts", {}).get(str(elem_base))
                if layout is None:
                    return None
                # Element size must be the struct size.
                elem_sz = int(getattr(layout, "size", 0))
                if elem_sz <= 0:
                    return None

                blob = bytearray([0] * (n * elem_sz))

                members = list(getattr(layout, "member_offsets", {}).keys())
                offsets = getattr(layout, "member_offsets", {})
                sizes = getattr(layout, "member_sizes", {})

                # Each array element initializer should be a brace list (InitializerList)
                # or a scalar (treated as first member initializer).
                for idx, elem_init in enumerate(inits[:n]):
                    sub_inits = self._const_initializer_list(elem_init)
                    if sub_inits is None:
                        # allow scalar shorthand for first member
                        sub_inits = [elem_init]
                    base_off = idx * elem_sz
                    for midx, m in enumerate(members):
                        if midx >= len(sub_inits):
                            break
                        imm = self._const_expr_to_int(sub_inits[midx])
                        if imm is None:
                            return None
                        off = int(offsets.get(m, 0))
                        sz = int(sizes.get(m, 4))
                        v = int(imm)
                        for i in range(min(sz, 8)):
                            blob[base_off + off + i] = (v >> (8 * i)) & 0xFF

                return "blob:" + blob.hex()

            # Unsized array-of-struct declared like `struct S a[] = {...}` is
            # recorded with decl.array_size=None and decl.type.base="struct S".
            # We handle it here by inferring element count from initializer.
            if self._is_struct_or_union_type(elem_base) and getattr(decl, "array_size", None) is None:
                # (Already covered above if we inferred `n`.) Keep for clarity.
                pass

            return None

        # Struct/union
        if self._is_struct_or_union_type(base):
            # Support nested initializer lists for structs/unions using
            # member-order mapping with brace elision and zero-fill.
            # Check for designated initializers first.
            if isinstance(init, Initializer) and any(d is not None for d, _v in (init.elements or [])):
                return self._const_designated_struct_blob(str(base), init, decl)
            inits0 = self._const_initializer_list(init)
            if inits0 is None:
                return None
            if self._sema_ctx is None:
                return None
            layout = getattr(self._sema_ctx, "layouts", {}).get(str(base))
            if layout is None:
                return None

            # (We no longer flatten scalars for structs; nested aggregate member
            # boundaries matter. We'll write directly from the initializer AST.)

            size = int(getattr(layout, "size", 0))
            blob = bytearray([0] * size)

            members = list(getattr(layout, "member_offsets", {}).keys())
            offsets = getattr(layout, "member_offsets", {})
            sizes = getattr(layout, "member_sizes", {})

            # If semantics doesn't encode padding (e.g. offsets are 0,4 for two ints
            # but struct size is 16), fall back to ABI-like packing using member_types.
            # NOTE: this fallback only supports scalar members.
            need_fallback = False
            try:
                if members and size > 0:
                    # For 2x int, expected size is 8; if larger, offsets likely wrong.
                    max_end = 0
                    for m in members:
                        off = int(offsets.get(m, 0))
                        sz = int(sizes.get(m, 4))
                        max_end = max(max_end, off + sz)
                    if max_end > 0 and size > max_end:
                        # If the gap is bigger than trailing padding (>=4), suspect missing padding.
                        if (size - max_end) >= 4 and any(int(offsets.get(m, 0)) == 4 for m in members):
                            need_fallback = True
            except Exception:
                need_fallback = False

            if need_fallback:
                mtypes = getattr(layout, "member_types", None)
                if not isinstance(mtypes, dict):
                    return None
                out = bytearray()
                cur = 0
                for midx, m in enumerate(members):
                    if midx >= len(inits0):
                        break
                    mty = mtypes.get(m)
                    if not isinstance(mty, str):
                        return None
                    # This fallback cannot handle aggregate members.
                    if self._is_struct_or_union_type(mty) or mty.startswith("array("):
                        return None
                    align = _type_align(mty)
                    sz = self._sizeof(mty)
                    if align > 1:
                        pad = (-cur) % align
                        if pad:
                            out.extend(b"\x00" * pad)
                            cur += pad
                    imm = self._const_expr_to_int(inits0[midx])
                    if imm is None:
                        return None
                    v = int(imm)
                    for i in range(min(sz, 8)):
                        out.append((v >> (8 * i)) & 0xFF)
                    cur += sz
                if len(out) < size:
                    out.extend(b"\x00" * (size - len(out)))
                return "blob:" + out.hex()

            # Normal case: use semantics-provided member offsets/sizes.
            # For structs/unions, initializer elements map to members in order.
            # If a member is itself an aggregate, its initializer element must
            # be handled as a sub-initializer (brace list or scalar with brace
            # elision), rather than flattening scalars across member boundaries.

            def _write_struct_from_init(ty_name: str, init_any: Any, base_off: int, blob_ref: bytearray) -> bool:
                layout3 = getattr(self._sema_ctx, "layouts", {}).get(str(ty_name))
                if layout3 is None:
                    return False
                members3 = list(getattr(layout3, "member_offsets", {}).keys())
                offsets3 = getattr(layout3, "member_offsets", {})
                sizes3 = getattr(layout3, "member_sizes", {})
                mtypes3 = getattr(layout3, "member_types", {})

                elems3 = self._const_initializer_list(init_any)
                if elems3 is None:
                    # scalar shorthand initializes first member only
                    elems3 = [init_any]

                # Important: elems3 elements can include nested Initializer
                # nodes. We must not treat a nested brace list as "available"
                # to later scalar members.

                def _member_consumption_count(mty: str) -> int:
                    # How many *top-level* initializer elements should be
                    # consumed for this member when braces are elided.
                    # For a nested struct/union member initialized by scalars
                    # (e.g. `{1,2,3}`), scalars continue into the submembers.
                    if self._is_struct_or_union_type(mty):
                        layout_n = getattr(self._sema_ctx, "layouts", {}).get(str(mty))
                        if layout_n is None:
                            return 1
                        return max(1, len(getattr(layout_n, "member_offsets", {}) or {}))
                    # Arrays are not used in the current tests; keep minimal.
                    return 1

                eidx = 0
                for m in members3:
                    mty = mtypes3.get(m)
                    member_off = base_off + int(offsets3.get(m, 0))
                    msz = int(sizes3.get(m, 0))

                    # If we ran out of initializer elements, remaining members
                    # stay zero-filled.
                    if eidx >= len(elems3):
                        break

                    # Aggregate members (struct/union/array): take exactly one
                    # initializer element for the member, and pack it recursively.
                    if isinstance(mty, str) and (self._is_struct_or_union_type(mty) or mty.startswith("array(")):
                        elem0 = elems3[eidx]
                        # If the element is a brace list for this member (e.g.
                        # `{1,{2}}`), consume exactly one element.
                        if isinstance(elem0, Initializer):
                            sub_blob = self._const_initializer_blob_for_type(str(mty), elem0)
                            if sub_blob is None:
                                return False
                            sub_bytes = bytes.fromhex(sub_blob.split(":", 1)[1])
                            end = min(len(blob_ref), member_off + len(sub_bytes))
                            blob_ref[member_off:end] = sub_bytes[: max(0, end - member_off)]
                            eidx += 1
                            continue
                        # If braces are elided and the member is a nested struct,
                        # consume following scalar elements into that member.
                        if self._is_struct_or_union_type(mty):
                            take = _member_consumption_count(str(mty))
                            sub_init = Initializer(
                                elements=[],
                                line=getattr(decl, "line", 0),
                                column=getattr(decl, "column", 0),
                            )
                            for j in range(take):
                                if eidx + j >= len(elems3):
                                    break
                                if isinstance(elems3[eidx + j], Initializer):
                                    break
                                sub_init.elements.append((None, elems3[eidx + j]))
                            elem_any = sub_init
                            consumed = len(sub_init.elements)
                        else:
                            elem_any = elem0
                            consumed = 1

                        # Pack aggregate member from constructed sub-initializer.
                        sub_blob = self._const_initializer_blob_for_type(str(mty), elem_any)
                        if sub_blob is None:
                            return False
                        sub_bytes = bytes.fromhex(sub_blob.split(":", 1)[1])
                        end = min(len(blob_ref), member_off + len(sub_bytes))
                        blob_ref[member_off:end] = sub_bytes[: max(0, end - member_off)]
                        eidx += max(1, consumed)
                        continue

                    # Scalar member: element must be a scalar expression.
                    if isinstance(elems3[eidx], Initializer):
                        return False
                    imm = self._const_expr_to_int(elems3[eidx])
                    if imm is None:
                        return False
                    v = int(imm)
                    sz = msz if msz > 0 else 4
                    for i in range(min(sz, 8)):
                        if 0 <= member_off + i < len(blob_ref):
                            blob_ref[member_off + i] = (v >> (8 * i)) & 0xFF
                    eidx += 1

                # Reject excess elements.
                if eidx < len(elems3):
                    raise IRGenError(
                        f"excess elements in initializer for '{ty_name}'"
                    )

                return True

            if not _write_struct_from_init(str(base), init, 0, blob):
                return None

            # C89 union initialization: only one initializer element is allowed
            # (it initializes the first member). Reject any excess elements.
            try:
                if str(base).strip().startswith("union "):
                    inits_top2 = self._const_initializer_list(init) or []
                    if len(inits_top2) > 1:
                        raise IRGenError(
                            f"excess elements in initializer for '{str(base).strip()}'"
                        )
            except IRGenError:
                raise
            except Exception:
                pass

            # Defensive: if nested aggregate packing failed to write but a nested
            # brace-list element exists, try a simple direct copy path for the
            # common case `{..., {scalar...}, ...}`. This keeps us correct for
            # global/static init of nested structs while the full packer is being
            # stabilized.
            try:
                inits_top = self._const_initializer_list(init) or []
                mtypes_top = getattr(layout, "member_types", {}) or {}
                if isinstance(mtypes_top, dict) and isinstance(inits_top, list):
                    for midx, m in enumerate(members):
                        if midx >= len(inits_top):
                            break
                        mty = mtypes_top.get(m)
                        if isinstance(mty, str) and self._is_struct_or_union_type(mty) and isinstance(inits_top[midx], Initializer):
                            off = int(offsets.get(m, 0))
                            sub_blob = self._const_initializer_blob_for_type(mty, inits_top[midx])
                            if sub_blob is None:
                                continue
                            sub_bytes = bytes.fromhex(sub_blob.split(":", 1)[1])
                            end = min(len(blob), off + len(sub_bytes))
                            blob[off:end] = sub_bytes[: max(0, end - off)]
            except Exception:
                pass

            return "blob:" + blob.hex()

        return None

    def _const_initializer_blob_for_type(self, ty_name: str, init_any: Any) -> Optional[str]:
        """Build a constant initializer blob for an arbitrary type.

        This is a helper for recursive aggregate members (e.g. struct members
        that are arrays). It is intentionally a small wrapper around the
        existing declaration-based blob packer.
        """

        class _FakeDecl:
            def __init__(self, name: str, type_name: str, initializer: Any):
                self.name = name
                self.type = type_name
                self.initializer = initializer
                self.line = getattr(initializer, "line", 0)
                self.column = getattr(initializer, "column", 0)

        fake = _FakeDecl("__pycc_const_init__", str(ty_name), init_any)
        return self._const_initializer_blob(fake)  # type: ignore[arg-type]

    def _const_designated_struct_blob(self, base: str, init: Initializer, decl: Declaration) -> Optional[str]:
        """Build a constant blob for a struct/union with designated initializers."""
        if self._sema_ctx is None:
            return None
        layout = getattr(self._sema_ctx, "layouts", {}).get(str(base))
        if layout is None:
            return None

        size = int(getattr(layout, "size", 0))
        blob = bytearray([0] * size)

        members = list(layout.member_offsets.keys())
        offsets = layout.member_offsets
        sizes = layout.member_sizes
        mtypes = getattr(layout, "member_types", {}) or {}

        # Build member -> value mapping from designated initializer.
        member_values: dict[str, Any] = {}
        cur_idx = 0

        for desig, val in (init.elements or []):
            if desig is not None and isinstance(desig, Designator):
                if desig.member is not None and desig.member in offsets:
                    member_values[desig.member] = val
                    try:
                        cur_idx = members.index(desig.member) + 1
                    except ValueError:
                        cur_idx = len(members)
            else:
                if cur_idx < len(members):
                    member_values[members[cur_idx]] = val
                    cur_idx += 1

        # Write values into blob at correct offsets.
        for m in members:
            val = member_values.get(m)
            if val is None:
                continue  # already zero-filled
            off = int(offsets.get(m, 0))
            sz = int(sizes.get(m, 4))
            mty = mtypes.get(m, "")

            if isinstance(val, Initializer) and isinstance(mty, str) and self._is_struct_or_union_type(mty):
                sub_blob = self._const_initializer_blob_for_type(str(mty), val)
                if sub_blob is None:
                    return None
                sub_bytes = bytes.fromhex(sub_blob.split(":", 1)[1])
                end = min(len(blob), off + len(sub_bytes))
                blob[off:end] = sub_bytes[:max(0, end - off)]
            else:
                imm = self._const_expr_to_int(val)
                if imm is None:
                    return None
                v = int(imm)
                for i in range(min(sz, 8)):
                    if 0 <= off + i < len(blob):
                        blob[off + i] = (v >> (8 * i)) & 0xFF

        return "blob:" + blob.hex()

    def _const_designated_array_blob(self, decl: Declaration, init: Initializer, n: int) -> Optional[str]:
        """Build a constant blob for an array with designated initializers."""
        base = getattr(decl.type, "base", None)
        if isinstance(decl.type, ArrayType):
            elem_ty = getattr(decl.type, "element_type", None)
            elem_base = str(getattr(elem_ty, "base", base)).strip()
        else:
            elem_base = str(base).strip() if base is not None else ""

        # Determine element size.
        if elem_base in {"char", "unsigned char"}:
            elem_sz = 1
        elif elem_base in {"int", "unsigned int"}:
            elem_sz = 4
        elif elem_base in {"long", "unsigned long", "long int", "unsigned long int"}:
            elem_sz = 8
        else:
            return None  # unsupported element type for designated array blob

        blob = bytearray([0] * (n * elem_sz))

        # Build index -> value mapping.
        index_values: dict[int, Any] = {}
        cur_idx = 0

        for desig, val in (init.elements or []):
            if desig is not None and isinstance(desig, Designator):
                if desig.index is not None:
                    try:
                        idx = _eval_const_int_expr(desig.index)
                    except Exception:
                        return None
                    index_values[idx] = val
                    cur_idx = idx + 1
            else:
                index_values[cur_idx] = val
                cur_idx += 1

        # Write values into blob.
        for idx in range(n):
            val = index_values.get(idx)
            if val is None:
                continue  # already zero-filled
            imm = self._const_expr_to_int(val)
            if imm is None:
                return None
            off = idx * elem_sz
            v = int(imm)
            if elem_sz == 1:
                blob[off] = v & 0xFF
            else:
                for i in range(min(elem_sz, 8)):
                    if 0 <= off + i < len(blob):
                        blob[off + i] = (v >> (8 * i)) & 0xFF

        return "blob:" + blob.hex()

    def _const_expr_to_int(self, expr: Any) -> Optional[int]:
        """Best-effort const int evaluator for global initializers."""
        if expr is None:
            return None
        if isinstance(expr, IntLiteral):
            return int(expr.value)
        if isinstance(expr, CharLiteral):
            return ord(expr.value)
        if isinstance(expr, UnaryOp) and expr.operator in {"+", "-", "~", "!"}:
            v = self._const_expr_to_int(expr.operand)
            if v is None:
                return None
            if expr.operator == "+": return v
            if expr.operator == "-": return -v
            if expr.operator == "~": return ~v
            return 0 if v != 0 else 1
        if isinstance(expr, BinaryOp):
            l = self._const_expr_to_int(expr.left)
            r = self._const_expr_to_int(expr.right)
            if l is None or r is None:
                return None
            op = expr.operator
            if op == "+": return l + r
            if op == "-": return l - r
            if op == "*": return l * r
            if op == "/": return int(l / r) if r != 0 else None
            if op == "%": return l % r if r != 0 else None
            if op == "|": return l | r
            if op == "&": return l & r
            if op == "^": return l ^ r
            if op == "<<": return l << r
            if op == ">>": return l >> r
        if isinstance(expr, Cast):
            return self._const_expr_to_int(expr.expression)
        if isinstance(expr, Identifier):
            v = getattr(expr, '_enum_value', None)
            if v is not None:
                return int(v)
            if expr.name in getattr(self, "_enum_constants", {}):
                return self._enum_constants[expr.name]
        return None

    def _const_expr_to_float(self, expr: Any) -> Optional[float]:
        """Best-effort const float evaluator for global initializers."""
        if expr is None:
            return None
        if isinstance(expr, FloatLiteral):
            return float(expr.value)
        if isinstance(expr, IntLiteral):
            return float(expr.value)
        if isinstance(expr, UnaryOp) and expr.operator == "-":
            v = self._const_expr_to_float(expr.operand)
            return -v if v is not None else None
        if isinstance(expr, UnaryOp) and expr.operator == "+":
            return self._const_expr_to_float(expr.operand)
        if isinstance(expr, Cast):
            return self._const_expr_to_float(expr.expression)
        if isinstance(expr, BinaryOp) and expr.operator == "*":
            l = self._const_expr_to_float(expr.left)
            r = self._const_expr_to_float(expr.right)
            if l is not None and r is not None:
                return l * r
        return None

    def _scalar_pack_info(self, elem_base: str):
        """Return (elem_size, pack_fn) for a scalar type, or None.

        pack_fn(expr) -> Optional[bytes]: converts a constant expression to
        its little-endian binary representation, or None if not constant.
        This is the single source of truth for scalar element packing in
        constant initializer blobs — no per-type if/elif branches needed.
        """
        def _pack_int(expr, mask, fmt):
            v = self._const_expr_to_int(expr)
            if v is None:
                return None
            return _struct.pack(fmt, v & mask)

        def _pack_float(expr, fmt):
            v = self._const_expr_to_float(expr)
            if v is None:
                # Allow integer literals in float context (e.g. {1, 0, 0})
                iv = self._const_expr_to_int(expr)
                if iv is not None:
                    v = float(iv)
            if v is None:
                return None
            return _struct.pack(fmt, v)

        def _pack_long_double(expr):
            v = self._const_expr_to_float(expr)
            if v is None:
                iv = self._const_expr_to_int(expr)
                if iv is not None:
                    v = float(iv)
            if v is None:
                return None
            # x86-64: 80-bit extended stored in 16-byte slot
            return _struct.pack("<d", v) + b'\x00' * 8

        _TABLE = {
            "char":           (1, lambda e: _pack_int(e, 0xFF, "<B")),
            "signed char":    (1, lambda e: _pack_int(e, 0xFF, "<B")),
            "unsigned char":  (1, lambda e: _pack_int(e, 0xFF, "<B")),
            "short":          (2, lambda e: _pack_int(e, 0xFFFF, "<H")),
            "signed short":   (2, lambda e: _pack_int(e, 0xFFFF, "<H")),
            "unsigned short": (2, lambda e: _pack_int(e, 0xFFFF, "<H")),
            "int":            (4, lambda e: _pack_int(e, 0xFFFFFFFF, "<I")),
            "signed int":     (4, lambda e: _pack_int(e, 0xFFFFFFFF, "<I")),
            "unsigned int":   (4, lambda e: _pack_int(e, 0xFFFFFFFF, "<I")),
            "long":           (8, lambda e: _pack_int(e, 0xFFFFFFFFFFFFFFFF, "<Q")),
            "signed long":    (8, lambda e: _pack_int(e, 0xFFFFFFFFFFFFFFFF, "<Q")),
            "unsigned long":  (8, lambda e: _pack_int(e, 0xFFFFFFFFFFFFFFFF, "<Q")),
            "float":          (4, lambda e: _pack_float(e, "<f")),
            "double":         (8, lambda e: _pack_float(e, "<d")),
            "long double":    (16, _pack_long_double),
        }
        return _TABLE.get(elem_base)

    def _resolve_elem_type(self, name: str) -> str:
        """Resolve a type name through typedefs to its underlying primitive."""
        _KNOWN = {"char", "unsigned char", "signed char",
                  "short", "unsigned short", "int", "unsigned int",
                  "long", "unsigned long", "float", "double", "long double",
                  "void"}
        if name in _KNOWN:
            return name
        # Already a struct/union literal name — no further resolution needed.
        if name.startswith("struct ") or name.startswith("union "):
            return name
        if self._sema_ctx is not None:
            td = getattr(self._sema_ctx, "typedefs", {}).get(name)
            if td is not None:
                rb = str(getattr(td, "base", "")).strip()
                if rb:
                    return self._resolve_elem_type(rb)
        return name

    def _is_volatile_sym(self, sym: str) -> bool:
        """Check if an IR symbol refers to a volatile-qualified variable.

        Checks the per-function _var_volatile set (populated from Declaration
        AST nodes) and falls back to the semantic context's global_decl_types
        for global variables.
        """
        if not isinstance(sym, str):
            return False
        # Check per-function volatile set (locals + params).
        if sym in getattr(self, "_var_volatile", set()):
            return True
        # Check global variables via semantic context.
        if sym.startswith("@") and self._sema_ctx is not None:
            name = sym[1:]
            gdt = getattr(self._sema_ctx, "global_decl_types", {})
            ty = gdt.get(name)
            if ty is not None and getattr(ty, "is_volatile", False):
                return True
        return False

    def _is_volatile_deref(self, ptr_expr: Expression) -> bool:
        """Check if dereferencing ptr_expr accesses volatile-qualified memory.

        For `*p` where `p` is `volatile int *`, the pointee is volatile.
        We check the declared type of the pointer variable for is_volatile
        (which qualifies the pointed-to object).
        """
        if isinstance(ptr_expr, Identifier):
            # Check local declaration types via semantic context.
            if self._sema_ctx is not None:
                # Try local decl types first (stored during semantic analysis).
                ty = getattr(self._sema_ctx, "global_decl_types", {}).get(ptr_expr.name)
                if ty is not None and getattr(ty, "is_volatile", False):
                    return True
            # Also check if the pointer variable itself is in our volatile set.
            sym = self._resolve_name(ptr_expr.name)
            if self._is_volatile_sym(sym):
                return True
        return False

    def _is_unsigned_operand(self, op: str) -> bool:
        """Best-effort check whether an operand is unsigned.

        We only use this for comparison lowering in the current milestone.
        Operands are IR strings like:
        - locals: "@x"
        - immediates: "$5"
        - temps: "%t0"

        We conservatively treat immediates as signed.
        """

        if not isinstance(op, str):
            return False
        if op.startswith("%"):
            ty = getattr(self, "_var_types", {}).get(op)
            if isinstance(ty, str) and ty.strip().lower().startswith("unsigned "):
                return True
        if op.startswith("@"):  # locals / globals
            # local type table (populated from decl/param operand1)
            ty = getattr(self, "_var_types", {}).get(op)
            if isinstance(ty, str):
                ty_norm = ty.strip().lower()
                if ty_norm.startswith("unsigned "):
                    return True
            # global type table (from semantic pass)
            if self._sema_ctx is not None:
                g = getattr(self._sema_ctx, "global_types", {})
                # stored without '@'
                ty2 = g.get(op[1:])
                if isinstance(ty2, str):
                    ty2_norm = ty2.strip().lower()
                    if ty2_norm.startswith("unsigned "):
                        return True
        return False

    def _normalize_int_type(self, ty: str) -> str:
        if not isinstance(ty, str):
            return ""
        t = ty.strip().lower()
        # collapse enum to int for arithmetic in this milestone
        if t.startswith("enum "):
            return "int"
        # normalize common spellings
        if t in {"signed", "signed int"}:
            return "int"
        if t in {"unsigned", "unsigned int"}:
            return "unsigned int"
        if t.startswith("signed char"):
            return "signed char"
        if t == "char":
            return "char"
        if t.startswith("unsigned char"):
            return "unsigned char"
        if t.startswith("short") and not t.startswith("unsigned"):
            return "short"
        if t.startswith("unsigned short"):
            return "unsigned short"
        if t.startswith("long") and not t.startswith("unsigned"):
            return "long"
        if t.startswith("unsigned long"):
            return "unsigned long"
        if t.startswith("int"):
            return "int"
        return t

    def _is_int_like_type(self, ty: str) -> bool:
        t = self._normalize_int_type(ty)
        if not t:
            return False
        if "*" in t:
            return False
        return t in {
            "char",
            "signed char",
            "unsigned char",
            "short",
            "unsigned short",
            "int",
            "unsigned int",
            "long",
            "unsigned long",
        }

    def _int_rank(self, ty: str) -> int:
        t = self._normalize_int_type(ty)
        return {
            "char": 1,
            "signed char": 1,
            "unsigned char": 1,
            "short": 2,
            "unsigned short": 2,
            "int": 3,
            "unsigned int": 3,
            "long": 4,
            "unsigned long": 4,
        }.get(t, 0)

    def _is_unsigned_type(self, ty: str) -> bool:
        t = self._normalize_int_type(ty)
        return t.startswith("unsigned ")

    def _integer_promote(self, ty: str) -> str:
        """C89 integer promotions (simplified for current model)."""
        t = self._normalize_int_type(ty)
        if t in {"char", "signed char", "unsigned char", "short"}:
            # On x86-64 SysV (int is 32-bit), these promote to int.
            return "int"
        if t in {"unsigned short"}:
            # On this target, unsigned short promotes to int because int
            # can represent all values of unsigned short.
            return "int"
        if t in {"int", "unsigned int", "long", "unsigned long"}:
            return t
        return t

    def _usual_arithmetic_conversion(self, lty: str, rty: str) -> str:
        """Return common real type for binary op (integer-only subset)."""
        lt = self._integer_promote(lty)
        rt = self._integer_promote(rty)

        # If either side is not an integer-like type, we can't apply integer UAC.
        if not self._is_int_like_type(lt) or not self._is_int_like_type(rt):
            return ""

        # After integer promotions, if both types are the same, keep it.
        # This matters for (unsigned short ? ... : ...) where both arms promote
        # to int on typical targets.
        if lt == rt:
            return lt

        # If either is unsigned long, result unsigned long.
        if lt == "unsigned long" or rt == "unsigned long":
            return "unsigned long"
        # long with unsigned int: on LP64, long can represent all u32.
        if (lt == "long" and rt == "unsigned int") or (rt == "long" and lt == "unsigned int"):
            return "long"
        # If either is long, result long.
        if lt == "long" or rt == "long":
            return "long"
        # If either is unsigned int, result unsigned int.
        if lt == "unsigned int" or rt == "unsigned int":
            return "unsigned int"
        return "int"

    def _operand_type_string(self, op: str) -> str:
        if not isinstance(op, str):
            return ""
        if op.startswith("%"):
            return str(getattr(self, "_var_types", {}).get(op, ""))
        if op.startswith("@"):
            # locals first
            ty = getattr(self, "_var_types", {}).get(op, "")
            if ty:
                return str(ty)
            # globals
            if self._sema_ctx is not None:
                g = getattr(self._sema_ctx, "global_types", {})
                return str(g.get(op[1:], ""))
        return ""

    def _ensure_u32(self, op: str) -> str:
        """Ensure operand is treated as 32-bit unsigned (zero-extended)."""
        t = self._new_temp()
        self._var_types[t] = "unsigned int"
        self.instructions.append(IRInstruction(op="zext32", result=t, operand1=op))
        return t

    def _ensure_u64(self, op: str) -> str:
        """Ensure operand is treated as 64-bit unsigned.

        On x86-64, values are already held in 64-bit registers; we mainly
        preserve type info for comparisons/division selection in codegen.
        """
        if isinstance(op, str) and op.startswith("%"):
            # Preserve existing temp but annotate as unsigned long.
            self._var_types[op] = "unsigned long"
            return op
        t = self._new_temp()
        self._var_types[t] = "unsigned long"
        self.instructions.append(IRInstruction(op="mov", result=t, operand1=op))
        return t

    def _try_struct_member_init(self, decl: Declaration, sc: str) -> bool:
        """Try to emit a gdef_struct IR instruction for a struct/union initializer.

        Handles structs with mixed member types including function pointers
        and symbol references that the blob path cannot encode.

        Returns True if successful (instruction emitted), False otherwise.
        """
        init = getattr(decl, "initializer", None)
        if not isinstance(init, Initializer):
            return False
        if self._sema_ctx is None:
            return False

        base = getattr(decl.type, "base", "")
        if isinstance(base, str):
            base = self._resolve_elem_type(base.strip())
        if not self._is_struct_or_union_type(base):
            return False

        layout = getattr(self._sema_ctx, "layouts", {}).get(str(base))
        if layout is None:
            return False

        inits0 = self._const_initializer_list(init)
        if inits0 is None:
            return False

        members = list(getattr(layout, "member_offsets", {}).keys())
        offsets = getattr(layout, "member_offsets", {})
        sizes = getattr(layout, "member_sizes", {})
        mtypes = getattr(layout, "member_types", {})
        struct_size = int(getattr(layout, "size", 0))

        # Build member descriptors: list of (kind, size, value)
        # kind: "int", "symbol", "float", "zero"
        member_descs = []
        prev_end = 0

        for midx, m in enumerate(members):
            off = int(offsets.get(m, 0))
            sz = int(sizes.get(m, 8))
            mty = mtypes.get(m, "")

            # Emit padding before this member
            if off > prev_end:
                member_descs.append(("zero", off - prev_end, 0))

            if midx >= len(inits0):
                # Remaining members zero-filled
                member_descs.append(("zero", sz, 0))
                prev_end = off + sz
                continue

            elem = inits0[midx]

            # Try integer constant
            imm = self._const_expr_to_int(elem)
            if imm is not None:
                member_descs.append(("int", sz, int(imm)))
                prev_end = off + sz
                continue

            # Try float constant
            fv = self._const_expr_to_float(elem)
            if fv is not None:
                member_descs.append(("float", sz, float(fv)))
                prev_end = off + sz
                continue

            # Try symbol reference (function name, global variable)
            if isinstance(elem, Identifier):
                member_descs.append(("symbol", sz, elem.name))
                prev_end = off + sz
                continue

            # Try cast of 0 to pointer (NULL)
            if isinstance(elem, Cast):
                inner = self._const_expr_to_int(elem.expression)
                if inner is not None:
                    member_descs.append(("int", sz, int(inner)))
                    prev_end = off + sz
                    continue

            # Unsupported member initializer
            return False

        # Trailing padding
        if prev_end < struct_size:
            member_descs.append(("zero", struct_size - prev_end, 0))

        self.instructions.append(
            IRInstruction(
                op="gdef_struct",
                result=f"@{decl.name}",
                operand1=str(base),
                label=sc,
                meta={"members": member_descs, "size": struct_size},
            )
        )
        return True

    def _const_initializer_imm(self, init: Any) -> Optional[str]:
        """Return an immediate like "$42" for supported constant initializers."""
        from pycc.ast_nodes import IntLiteral, CharLiteral, UnaryOp

        if isinstance(init, IntLiteral):
            return f"${int(init.value)}"
        if isinstance(init, CharLiteral):
            # CharLiteral.value is a single-character string (e.g. "h").
            # Use its code point as the integer value.
            return f"${ord(init.value)}"
        if isinstance(init, UnaryOp) and init.operator in {"+", "-"}:
            inner = self._const_initializer_imm(init.operand)
            if inner is None:
                return None
            v = int(inner.lstrip("$"))
            if init.operator == "-":
                v = -v
            return f"${v}"
        return None

    def _const_initializer_ptr(self, init: Any) -> Optional[str]:
        """Return a pointer constant operand for supported global pointer initializers.

        Currently supports only string literals, encoded as a tagged operand
        starting with "=str:"; codegen will intern the string and emit a
        relocatable address.
        """
        from pycc.ast_nodes import StringLiteral

        if isinstance(init, StringLiteral):
            return f"=str:{init.value}"
        return None

    def _const_initializer_list(self, init: Any) -> Optional[list[Any]]:
        """Decode a non-designated initializer-list into a flat list.

        Used by both local aggregate initialization helpers and the global
        constant-initializer blob packer.
        """

        if isinstance(init, Initializer):
            return [e for (_d, e) in (init.elements or [])]
        # Allow `char s[] = "..."` to be treated like an initializer-list with one element.
        # The parser currently represents this as a plain StringLiteral expression.
        if isinstance(init, StringLiteral):
            return [init]
        return None

    # Helpers

    def _new_temp(self) -> str:
        t = f"%t{self.temp_counter}"
        self.temp_counter += 1
        return t

    def _new_temp_typed(self, ctype: CType) -> str:
        """Create a new temp and register its CType in both _sym_table and _var_types."""
        name = self._new_temp()
        if self._sym_table:
            self._sym_table.insert(name, ctype)
        self._var_types[name] = ctype_to_ir_type(ctype)
        return name

    def _pointee_size_from_ctype(self, operand: str) -> Optional[int]:
        """Return the byte size of the pointee type for a pointer operand, or None."""
        if not self._sym_table:
            return None
        ct = self._sym_table.lookup(operand)
        if ct is None:
            return None
        # PointerType: extract pointee size directly.
        if isinstance(ct, PointerType) and ct.pointee is not None:
            return type_sizeof(ct.pointee)
        # ArrayType: extract element size (array decays to pointer).
        if isinstance(ct, CArrayType) and ct.element is not None:
            return type_sizeof(ct.element)
        return None

    def _lookup_pointer_ctype(self, operand: str) -> Optional[CType]:
        """Look up the CType for an operand and return it if it is a pointer or array.

        Returns the CType if it is a PointerType or ArrayType, None otherwise.
        Used for propagating pointer types through arithmetic results.
        """
        if not self._sym_table:
            return None
        ct = self._sym_table.lookup(operand)
        if ct is None:
            return None
        if isinstance(ct, (PointerType, CArrayType)):
            return ct
        return None

    def _return_type_to_ctype(self, func_name: str) -> Optional[CType]:
        """Get the return CType for a function call from function_sigs.

        Looks up the function name in sema_ctx.function_sigs to get the
        return type string, then converts it to a CType via _str_to_ctype.
        Returns None if the function is not found or sema_ctx is unavailable.
        """
        if self._sema_ctx is None:
            return None
        sigs = getattr(self._sema_ctx, "function_sigs", None)
        if not isinstance(sigs, dict):
            return None
        sig = sigs.get(func_name)
        if sig is None:
            return None
        try:
            ret_base = str(sig[0])
        except Exception:
            return None
        if not ret_base or ret_base == "void":
            return None
        try:
            return _str_to_ctype(ret_base)
        except Exception:
            return None

    def _uac_result_ctype(self, lty_str: str, rty_str: str) -> Optional[CType]:
        """Compute the result CType for a binary operation using UAC rules.

        For integer operands, applies usual arithmetic conversions to determine
        the common type. For comparison operators, the result is always int.
        Returns None if types cannot be determined.
        """
        if not lty_str and not rty_str:
            return None
        # If either is a float type, determine common fp type.
        _FP = {"float", "double", "long double"}
        ln = lty_str.strip().lower() if lty_str else ""
        rn = rty_str.strip().lower() if rty_str else ""
        if ln in _FP or rn in _FP:
            if "long double" in (ln, rn):
                return FloatType(kind=TypeKind.DOUBLE)  # best approx for long double
            if "double" in (ln, rn):
                return FloatType(kind=TypeKind.DOUBLE)
            return FloatType(kind=TypeKind.FLOAT)
        # Integer UAC
        if self._is_int_like_type(lty_str) and self._is_int_like_type(rty_str):
            common = self._usual_arithmetic_conversion(lty_str, rty_str)
            if common:
                return _str_to_ctype(common)
        # Single side available
        if lty_str:
            try:
                return _str_to_ctype(lty_str)
            except Exception:
                pass
        return None

    def _insert_decl_ctype(self, ir_sym: str, decl) -> None:
        """Insert a local variable or parameter CType into the symbol table.

        Handles arrays (creating ArrayType), struct/union, pointers, and
        scalar types. Always uses ast_type_to_ctype_resolved for typedef
        resolution.
        """
        if not self._sym_table:
            return
        arr_sz = getattr(decl, "array_size", None)
        ast_type = getattr(decl, "type", None)
        if ast_type is None:
            return
        base_ctype = ast_type_to_ctype_resolved(ast_type, self._sema_ctx)
        if arr_sz is not None:
            # If base_ctype is already an ArrayType (e.g. from typedef array
            # resolution in ast_type_to_ctype_resolved), use it directly
            # instead of double-wrapping.
            if isinstance(base_ctype, CArrayType):
                self._sym_table.insert(ir_sym, base_ctype)
            else:
                # Array declaration: wrap element CType in ArrayType.
                # For multi-dim arrays, compute total element count.
                total = int(arr_sz)
                ad = getattr(decl, "array_dims", None)
                if isinstance(ad, list) and len(ad) >= 2:
                    prod = 1
                    for d in ad:
                        if isinstance(d, int):
                            prod *= d
                    if prod > total:
                        total = prod
                # base_ctype may already be a PointerType if the element is a
                # pointer (e.g. char *arr[N]). For arrays, the element type is
                # the full base_ctype (including pointer levels).
                arr_ctype = CArrayType(
                    kind=TypeKind.ARRAY,
                    element=base_ctype,
                    size=total,
                )
                self._sym_table.insert(ir_sym, arr_ctype)
        else:
            self._sym_table.insert(ir_sym, base_ctype)

    def _lookup_member_ctype(self, base: str, member: str) -> Optional[CType]:
        """Look up the CType of a struct/union member.

        Resolves the struct type from the base symbol (via _sym_table or
        _var_types), finds the StructLayout, and converts the member's
        AST declaration type to a CType via ast_type_to_ctype_resolved.

        Returns None if the layout or member type cannot be resolved.
        """
        if self._sema_ctx is None:
            return None
        layouts = getattr(self._sema_ctx, "layouts", {})
        if not layouts:
            return None

        # Determine the struct type name from the base symbol.
        struct_key = None

        # Strategy 1: Use _sym_table CType to get the struct tag.
        if self._sym_table:
            ct = self._sym_table.lookup(base)
            if ct is not None:
                # Unwrap pointer to get the struct type.
                inner = ct
                if isinstance(inner, PointerType) and inner.pointee is not None:
                    inner = inner.pointee
                if isinstance(inner, CStructType) and inner.tag is not None:
                    prefix = "union " if inner.kind == TypeKind.UNION else "struct "
                    struct_key = prefix + inner.tag

        # Strategy 2: Fall back to _var_types string.
        if struct_key is None:
            bty = self._var_types.get(base, "")
            if isinstance(bty, str):
                bty = bty.strip()
                if bty.endswith("*"):
                    bty = bty[:-1].strip()
                # Resolve typedef to find the layout key.
                resolved = self._resolve_elem_type(bty) if bty else bty
                if resolved and (resolved.startswith("struct ") or resolved.startswith("union ")):
                    struct_key = resolved
                elif bty and (bty.startswith("struct ") or bty.startswith("union ")):
                    struct_key = bty

        if struct_key is None:
            return None

        layout = layouts.get(struct_key)
        if layout is None:
            return None

        mdecl_types = getattr(layout, "member_decl_types", None)
        if not mdecl_types or member not in mdecl_types:
            return None

        return ast_type_to_ctype_resolved(mdecl_types[member], self._sema_ctx)

    def _member_ctype_from_layout(self, layout, member: str) -> Optional[CType]:
        """Get member CType directly from a StructLayout object.

        Used by initializer lowering paths that already have the layout.
        Returns None if member_decl_types is unavailable or member not found.
        """
        if layout is None or self._sema_ctx is None:
            return None
        mdecl_types = getattr(layout, "member_decl_types", None)
        if not mdecl_types or member not in mdecl_types:
            return None
        return ast_type_to_ctype_resolved(mdecl_types[member], self._sema_ctx)

    def _get_member_ctype(self, layout, member_name: str, sema_ctx=None) -> Optional[CType]:
        """Get a member's fully resolved CType from a StructLayout.

        Unlike _member_ctype_from_layout, this also handles array members
        by consulting layout.member_array_info and wrapping the element
        CType in ArrayType(s) for multi-dimensional arrays.

        Args:
            layout: StructLayout with member type info.
            member_name: Name of the struct/union member.
            sema_ctx: SemanticContext for typedef resolution. Falls back
                       to self._sema_ctx if None.

        Returns:
            Fully resolved CType (including ArrayType wrapping for array
            members), or None if the member type cannot be determined.
        """
        ctx = sema_ctx if sema_ctx is not None else self._sema_ctx
        if layout is None or ctx is None:
            return None
        mdecl_types = getattr(layout, "member_decl_types", None)
        if not mdecl_types or member_name not in mdecl_types:
            return None

        # Convert the element AST Type to a resolved CType.
        elem_ct = ast_type_to_ctype_resolved(mdecl_types[member_name], ctx)

        # Check if this member is an array.
        arr_info = getattr(layout, "member_array_info", None)
        if arr_info and member_name in arr_info:
            array_size, array_dims = arr_info[member_name]
            if isinstance(array_dims, list) and len(array_dims) >= 2:
                # Multi-dimensional: wrap from innermost to outermost.
                # array_dims is outer-to-inner, e.g. [2, 3] for int a[2][3].
                ct = elem_ct
                for dim in reversed(array_dims):
                    ct = CArrayType(
                        kind=TypeKind.ARRAY,
                        element=ct,
                        size=int(dim) if dim is not None else None,
                    )
                return ct
            else:
                # Single-dimension array.
                return CArrayType(
                    kind=TypeKind.ARRAY,
                    element=elem_ct,
                    size=int(array_size) if array_size is not None else None,
                )

        return elem_ct

    @staticmethod
    def _unwrap_single_init(init: Expression) -> Expression:
        """Unwrap a single-element brace initializer, e.g. ``int x = {42}`` → ``42``.

        If *init* is an ``Initializer`` node with exactly one element whose
        designator is ``None``, return that inner element.  Otherwise return
        *init* unchanged.  This implements the C89 rule that allows a scalar
        initializer to be optionally wrapped in braces.
        """
        if (
            isinstance(init, Initializer)
            and len(init.elements) == 1
            and init.elements[0][0] is None
        ):
            return init.elements[0][1]
        return init

    def _flatten_multidim_init(
        self,
        init: Expression,
        array_dims: list,
        line: int,
        column: int,
    ) -> Initializer:
        """Flatten a nested multi-dimensional initializer into a 1D list.

        For ``int a[2][3] = { {1,2,3}, {4,5,6} }``, produces a flat
        ``Initializer`` with elements ``[1,2,3,4,5,6]``.

        Handles both nested brace lists and brace elision (already flat).
        Each row is padded to the column count with zero-fill.
        """
        if not isinstance(init, Initializer):
            return init
        elems = init.elements or []
        cols = int(array_dims[1]) if len(array_dims) >= 2 else 1
        flat_elems: list = []
        has_nested = any(isinstance(e, Initializer) for _d, e in elems)
        if has_nested:
            for _desig, row in elems:
                if isinstance(row, Initializer):
                    row_vals = [e for (_d, e) in (row.elements or [])]
                    # Pad short rows to column count.
                    while len(row_vals) < cols:
                        row_vals.append(IntLiteral(
                            value=0, is_hex=False, is_octal=False,
                            line=line, column=column))
                    flat_elems.extend([(None, v) for v in row_vals[:cols]])
                else:
                    flat_elems.append((_desig, row))
        else:
            # Already flat (brace elision).
            flat_elems = list(elems)
        return Initializer(elements=flat_elems, line=line, column=column)

    def _count_flat_inits(self, ctype: CType) -> int:
        """Count the number of flat scalar elements in an aggregate type.

        Used for brace elision to determine how many elements to consume
        from a flat initializer list for a nested aggregate member.

        - Array: element_flat_count * size
        - Struct: sum of flat counts of all members
        - Union: flat count of first member (C89 rule)
        - Scalar: 1
        """
        ct = resolve_typedefs(ctype, self._sema_ctx)

        if ct.kind == TypeKind.ARRAY and isinstance(ct, CArrayType):
            elem_count = self._count_flat_inits(ct.element) if ct.element else 1
            size = ct.size if ct.size is not None else 0
            return elem_count * size

        if ct.kind in (TypeKind.STRUCT, TypeKind.UNION):
            tag = getattr(ct, 'tag', None)
            if tag is None:
                return 1
            # Build the layout key: "struct Tag" or "union Tag"
            prefix = 'union' if ct.kind == TypeKind.UNION else 'struct'
            layout_key = f"{prefix} {tag}"
            layouts = getattr(self._sema_ctx, 'layouts', {}) if self._sema_ctx else {}
            layout = layouts.get(layout_key)
            if layout is None:
                # Try the tag directly (e.g. typedef-registered layouts)
                layout = layouts.get(tag)
            if layout is None:
                return 1
            members = list(getattr(layout, 'member_offsets', {}) or {})
            if not members:
                return 1
            if ct.kind == TypeKind.UNION:
                # C89: only first member is initialized
                m_ct = self._get_member_ctype(layout, members[0])
                return self._count_flat_inits(m_ct) if m_ct else 1
            # Struct: sum of all members
            total = 0
            for m in members:
                m_ct = self._get_member_ctype(layout, m)
                total += self._count_flat_inits(m_ct) if m_ct else 1
            return total

        # Scalar types
        return 1

    # ── Unified initializer lowering entry point ───────────────────────

    def _lower_initializer(
        self,
        ctype: CType,
        init: Expression,
        base_sym: str,
        is_ptr: bool,
    ) -> None:
        """Unified recursive entry point for local initializer lowering.

        Resolves typedefs on *ctype*, then dispatches to the appropriate
        handler based on ``ctype.kind``:

        - ARRAY  → ``_lower_array_init``
        - STRUCT / UNION → ``_lower_struct_init``
        - scalar → ``_lower_scalar_init``

        Also handles the special case of ``struct S b = a;`` where *init*
        is not an ``Initializer`` node but a plain expression (struct copy).

        Args:
            ctype:    Fully constructed CType for the target variable.
            init:     AST initializer expression (Initializer node, or a
                      plain expression for struct-copy / scalar init).
            base_sym: IR symbol name (e.g. ``"@x"`` or ``"%t42"``).
            is_ptr:   Whether *base_sym* is a pointer to the target
                      (True when lowering nested aggregate members via
                      ``addr_of_member``).
        """
        # 1. Resolve typedefs to the underlying concrete type.
        ct = resolve_typedefs(ctype, self._sema_ctx)

        # 2. Struct/union copy: ``struct S b = a;`` — init is a plain
        #    expression, not an Initializer node.
        if ct.kind in (TypeKind.STRUCT, TypeKind.UNION) and not isinstance(init, Initializer):
            v = self._gen_expr(init)
            tag = getattr(ct, 'tag', None)
            prefix = 'union' if ct.kind == TypeKind.UNION else 'struct'
            layout_key = f"{prefix} {tag}" if tag else None
            layouts = getattr(self._sema_ctx, 'layouts', {}) if self._sema_ctx else {}
            layout = layouts.get(layout_key) if layout_key else None
            if layout is None and tag:
                layout = layouts.get(tag)
            sz = int(getattr(layout, 'size', 0) or 0) if layout else 0
            if sz > 0:
                self.instructions.append(
                    IRInstruction(op="struct_copy", result=base_sym,
                                  operand1=v, meta={"size": sz})
                )
            else:
                _vol = self._is_volatile_sym(base_sym)
                self.instructions.append(
                    IRInstruction(op="mov", result=base_sym, operand1=v,
                                  meta={"volatile": True} if _vol else None)
                )
            return

        # 3. Dispatch by CType kind.
        if ct.kind == TypeKind.ARRAY and isinstance(ct, CArrayType):
            self._lower_array_init(ct, init, base_sym)
            return

        if ct.kind in (TypeKind.STRUCT, TypeKind.UNION):
            self._lower_struct_init(ct, init, base_sym, is_ptr)
            return

        # 4. Scalar (int, float, char, pointer, enum, etc.)
        self._lower_scalar_init(ct, init, base_sym, is_ptr)

    # ── Stub handlers (to be replaced by tasks 2.1, 3.1–3.3, 4.1–4.3) ─

    def _lower_scalar_init(
        self,
        ctype: CType,
        init: Expression,
        base_sym: str,
        is_ptr: bool,
    ) -> None:
        """Lower a scalar initializer to IR instructions.

        Handles all scalar types uniformly: int, float, char, short, long,
        pointer, and enum.  When *is_ptr* is False, emits a ``mov``
        instruction (direct variable assignment).  When *is_ptr* is True
        (base_sym holds a pointer to the target, e.g. from addr_of_member),
        emits a ``store`` instruction (pointer dereference store).

        Braces around a scalar initializer (``int x = {42}``) are unwrapped
        before evaluation.  Volatile marking is applied when the target
        symbol is volatile-qualified.
        """
        init = self._unwrap_single_init(init)
        v = self._gen_expr(init)
        _vol = self._is_volatile_sym(base_sym)
        if is_ptr:
            # base_sym is a pointer to the target location — store through it.
            self.instructions.append(
                IRInstruction(op="store", result=v, operand1=base_sym,
                              meta={"volatile": True} if _vol else None)
            )
        else:
            # base_sym is the target variable itself — direct assignment.
            self.instructions.append(
                IRInstruction(op="mov", result=base_sym, operand1=v,
                              meta={"volatile": True} if _vol else None)
            )

    def _lower_array_init(
        self,
        ctype: CArrayType,
        init: Expression,
        base_sym: str,
    ) -> None:
        """Lower an array initializer to IR instructions.

        Handles:
        - String literal initialization for char/unsigned char arrays
        - General brace-enclosed initializer lists
        - Designated array initializers
        """
        elem_ct = resolve_typedefs(ctype.element, self._sema_ctx) if ctype.element else None

        # ── String literal path: char s[N] = "hello" or char s[] = "hello" ──
        if elem_ct is not None and elem_ct.kind == TypeKind.CHAR:
            str_lit = self._extract_string_literal(init)
            if str_lit is not None:
                s = str_lit.value
                n = ctype.size
                if n is None:
                    # Inferred size: char s[] = "hello" → size = len + 1
                    n = len(s) + 1
                else:
                    n = int(n)
                    if len(s) + 1 > n:
                        raise IRGenError(
                            f"string literal initializer too long for array '{base_sym}'"
                        )
                # Build byte values: string chars + NUL + zero-fill
                bytes_vals = [ord(c) for c in s]
                if len(bytes_vals) < n:
                    bytes_vals.append(0)  # NUL terminator
                if len(bytes_vals) > n:
                    bytes_vals = bytes_vals[:n]
                else:
                    bytes_vals = bytes_vals + [0] * (n - len(bytes_vals))
                for idx, b in enumerate(bytes_vals):
                    self.instructions.append(
                        IRInstruction(
                            op="store_index",
                            result=f"${b}",
                            operand1=base_sym,
                            operand2=f"${idx}",
                            label="char",
                        )
                    )
                return

        # ── General brace-enclosed initializer list ──
        if not isinstance(init, Initializer):
            raise IRGenError(
                f"unsupported array initializer for '{base_sym}': expected initializer list"
            )

        elems = init.elements or []
        n = ctype.size
        if n is None:
            # Unsized array: infer size from initializer count.
            n = len(elems)
        else:
            n = int(n)

        # Check for designated initializers.
        has_desig = any(d is not None for d, _e in elems)
        if has_desig:
            self._lower_array_init_designated(ctype, init, base_sym)
            return

        # Check excess elements.
        if len(elems) > n:
            raise IRGenError(
                f"excess elements in array initializer for '{base_sym}': "
                f"got {len(elems)}, expected at most {n}"
            )

        # Resolve element CType for dispatch decisions.
        elem_ct = resolve_typedefs(ctype.element, self._sema_ctx) if ctype.element else None
        is_aggregate = (
            elem_ct is not None
            and elem_ct.kind in (TypeKind.STRUCT, TypeKind.UNION, TypeKind.ARRAY)
        )

        # Determine IR type label for store_index (scalar path).
        ir_label = ctype_to_ir_type(elem_ct) if elem_ct is not None else "int"

        for idx in range(n):
            if idx < len(elems):
                _desig, elem_init = elems[idx]
            else:
                elem_init = None  # zero-fill

            if is_aggregate:
                # Aggregate element: compute address, recurse.
                elem_ptr_ct = PointerType(kind=TypeKind.POINTER, pointee=ctype.element)
                t_addr = self._new_temp_typed(elem_ptr_ct)
                self._var_types[t_addr] = ir_label + "*" if not ir_label.endswith("*") else ir_label
                self.instructions.append(
                    IRInstruction(
                        op="addr_index", result=t_addr,
                        operand1=base_sym, operand2=f"${idx}",
                    )
                )
                if elem_init is not None:
                    if not isinstance(elem_init, Initializer) and ctype.element is not None:
                        # Wrap bare expression in an Initializer for struct elements.
                        elem_init = Initializer(
                            elements=[(None, elem_init)],
                            line=getattr(init, 'line', 0),
                            column=getattr(init, 'column', 0),
                        )
                    self._lower_initializer(ctype.element, elem_init, t_addr, True)
                else:
                    # Zero-fill aggregate element via empty Initializer.
                    zero_init = Initializer(
                        elements=[],
                        line=getattr(init, 'line', 0),
                        column=getattr(init, 'column', 0),
                    )
                    self._lower_initializer(ctype.element, zero_init, t_addr, True)
            else:
                # Scalar element: use store_index directly.
                if elem_init is not None:
                    v = self._gen_expr(elem_init)
                else:
                    v = "$0"
                self.instructions.append(
                    IRInstruction(
                        op="store_index",
                        result=v,
                        operand1=base_sym,
                        operand2=f"${idx}",
                        label=ir_label,
                    )
                )

    def _lower_array_init_designated(
        self,
        ctype: CArrayType,
        init: Initializer,
        base_sym: str,
    ) -> None:
        """Lower a designated array initializer.

        Handles ``int a[5] = { [2] = 10, [0] = 5 }`` style initialization.
        Mixed designated/non-designated elements are supported: the sequential
        position advances after each designated element.  Unspecified indices
        are zero-filled.
        """
        elems = init.elements or []
        n = ctype.size
        if n is None:
            # Compute max index to infer size.
            max_idx = -1
            cur = 0
            for desig, _val in elems:
                if desig is not None:
                    idx = self._resolve_designator_index(desig)
                    if idx is not None:
                        max_idx = max(max_idx, idx)
                        cur = idx + 1
                    else:
                        max_idx = max(max_idx, cur)
                        cur += 1
                else:
                    max_idx = max(max_idx, cur)
                    cur += 1
            n = max_idx + 1 if max_idx >= 0 else 0
        else:
            n = int(n)

        # Build index → value mapping.  Non-designated elements advance
        # sequentially; designated elements set cur_idx to desig.index + 1.
        index_values: dict[int, Any] = {}
        cur_idx = 0
        for desig, val in elems:
            if desig is not None:
                idx = self._resolve_designator_index(desig)
                if idx is not None:
                    if idx >= n:
                        raise IRGenError(
                            f"array designator index {idx} out of bounds "
                            f"for '{base_sym}' of size {n}"
                        )
                    index_values[idx] = val
                    cur_idx = idx + 1
                else:
                    # Fallback: treat as sequential if index can't be resolved.
                    index_values[cur_idx] = val
                    cur_idx += 1
            else:
                if cur_idx >= n:
                    raise IRGenError(
                        f"excess elements in array initializer for '{base_sym}': "
                        f"index {cur_idx} exceeds size {n}"
                    )
                index_values[cur_idx] = val
                cur_idx += 1

        # Resolve element CType for dispatch decisions.
        elem_ct = resolve_typedefs(ctype.element, self._sema_ctx) if ctype.element else None
        is_aggregate = (
            elem_ct is not None
            and elem_ct.kind in (TypeKind.STRUCT, TypeKind.UNION, TypeKind.ARRAY)
        )
        ir_label = ctype_to_ir_type(elem_ct) if elem_ct is not None else "int"

        # Emit stores for [0, n), using designated values or zero-fill.
        for idx in range(n):
            elem_init = index_values.get(idx)

            if is_aggregate:
                # Aggregate element: compute address, recurse.
                elem_ptr_ct = PointerType(kind=TypeKind.POINTER, pointee=ctype.element)
                t_addr = self._new_temp_typed(elem_ptr_ct)
                self._var_types[t_addr] = ir_label + "*" if not ir_label.endswith("*") else ir_label
                self.instructions.append(
                    IRInstruction(
                        op="addr_index", result=t_addr,
                        operand1=base_sym, operand2=f"${idx}",
                    )
                )
                if elem_init is not None:
                    if not isinstance(elem_init, Initializer) and ctype.element is not None:
                        elem_init = Initializer(
                            elements=[(None, elem_init)],
                            line=getattr(init, 'line', 0),
                            column=getattr(init, 'column', 0),
                        )
                    self._lower_initializer(ctype.element, elem_init, t_addr, True)
                else:
                    zero_init = Initializer(
                        elements=[],
                        line=getattr(init, 'line', 0),
                        column=getattr(init, 'column', 0),
                    )
                    self._lower_initializer(ctype.element, zero_init, t_addr, True)
            else:
                # Scalar element: use store_index directly.
                if elem_init is not None:
                    v = self._gen_expr(elem_init)
                else:
                    v = "$0"
                self.instructions.append(
                    IRInstruction(
                        op="store_index",
                        result=v,
                        operand1=base_sym,
                        operand2=f"${idx}",
                        label=ir_label,
                    )
                )

    def _extract_string_literal(self, init: Expression) -> Optional[StringLiteral]:
        """Extract a StringLiteral from an initializer if present.

        Handles three forms:
        - Direct StringLiteral: ``char s[] = "hello"``
        - Initializer wrapping a StringLiteral: ``char s[] = {"hello"}``
        - Initializer with one element that is a StringLiteral
        Returns None if init is not a string literal form.
        """
        if isinstance(init, StringLiteral):
            return init
        if isinstance(init, Initializer):
            elems = init.elements or []
            if len(elems) == 1 and elems[0][0] is None:
                inner = elems[0][1]
                if isinstance(inner, StringLiteral):
                    return inner
        return None

    def _lower_struct_init(
        self,
        ctype: CType,
        init: Initializer,
        base_sym: str,
        is_ptr: bool,
    ) -> None:
        """Lower a struct/union initializer to IR instructions.

        Handles:
        - Sequential (non-designated) member initialization
        - Union initialization — first member only, per C89
        - Designated initializers

        For each member, uses CType-driven dispatch via _lower_initializer
        to recursively handle nested aggregates, brace elision, and
        trailing zero-fill.
        """
        ct = resolve_typedefs(ctype, self._sema_ctx)
        tag = getattr(ct, 'tag', None)
        if tag is None:
            raise IRGenError("_lower_struct_init: cannot determine struct/union tag")

        # Build the layout key: "struct Tag" or "union Tag".
        prefix = 'union' if ct.kind == TypeKind.UNION else 'struct'
        layout_key = f"{prefix} {tag}"
        layouts = getattr(self._sema_ctx, 'layouts', {}) if self._sema_ctx else {}
        layout = layouts.get(layout_key)
        if layout is None:
            # Try the tag directly (e.g. typedef-registered layouts).
            layout = layouts.get(tag)
        if layout is None:
            raise IRGenError(f"_lower_struct_init: no layout for '{layout_key}'")

        members = list(getattr(layout, 'member_offsets', {}) or {})
        src_line = getattr(init, 'line', 0)
        src_col = getattr(init, 'column', 0)

        # Extract initializer elements.
        if not isinstance(init, Initializer):
            raise IRGenError(
                f"_lower_struct_init: expected Initializer node for '{layout_key}'"
            )
        elems = init.elements or []

        # Check for designated initializers.
        if self._has_any_designator(init):
            self._lower_designated_struct_init_new(ct, init, base_sym, is_ptr)
            return

        # Union: only initialize the first member (C89 rule).
        if ct.kind == TypeKind.UNION:
            self._lower_union_init(ct, layout, members, elems, base_sym, is_ptr, src_line, src_col)
            return

        # Sequential struct initialization.
        eidx = 0
        for m in members:
            m_ct = self._get_member_ctype(layout, m)

            if eidx >= len(elems):
                # Zero-fill trailing unspecified members.
                self._zero_fill_member(layout, m, m_ct, base_sym, is_ptr, src_line, src_col)
                continue

            _desig, elem_init = elems[eidx]

            # Determine if this member is an aggregate type.
            m_ct_resolved = resolve_typedefs(m_ct, self._sema_ctx) if m_ct else None
            is_aggregate = (
                m_ct_resolved is not None
                and m_ct_resolved.kind in (TypeKind.STRUCT, TypeKind.UNION, TypeKind.ARRAY)
            )

            if is_aggregate and m_ct is not None:
                if isinstance(elem_init, Initializer):
                    # Braced sub-initializer for aggregate member — recurse.
                    eidx += 1
                else:
                    # Brace elision: member is aggregate but element is a bare
                    # expression.  Consume the correct number of flat elements.
                    take = self._count_flat_inits(m_ct)
                    sub_elems: list = []
                    for _ in range(take):
                        if eidx >= len(elems):
                            break
                        _d, e = elems[eidx]
                        if isinstance(e, Initializer):
                            break
                        sub_elems.append(e)
                        eidx += 1
                    elem_init = Initializer(
                        elements=[(None, e) for e in sub_elems],
                        line=src_line, column=src_col,
                    )

                # Get member address and recurse.
                ptr_ct = PointerType(kind=TypeKind.POINTER, pointee=m_ct)
                t_addr = self._new_temp_typed(ptr_ct)
                op_aom = "addr_of_member_ptr" if is_ptr else "addr_of_member"
                self.instructions.append(
                    IRInstruction(
                        op=op_aom, result=t_addr,
                        operand1=base_sym, operand2=m,
                        result_type=ptr_ct,
                    )
                )
                self._lower_initializer(m_ct, elem_init, t_addr, True)
            else:
                # Scalar member: evaluate expression and store directly.
                eidx += 1
                v = self._gen_expr(elem_init)
                meta = {"member_ctype": m_ct} if m_ct else None
                op_store = "store_member_ptr" if is_ptr else "store_member"
                self.instructions.append(
                    IRInstruction(
                        op=op_store, result=v,
                        operand1=base_sym, operand2=m,
                        meta=meta,
                    )
                )

        # Check for excess elements.
        if eidx < len(elems):
            raise IRGenError(
                f"excess elements in initializer for '{layout_key}'"
            )

    def _lower_union_init(
        self,
        ctype: CType,
        layout,
        members: list,
        elems: list,
        base_sym: str,
        is_ptr: bool,
        src_line: int,
        src_col: int,
    ) -> None:
        """Lower a union initializer — only the first member (C89 rule).

        Per C89, a union initializer initializes only the first declared
        member.  If the initializer list is empty, the first member is
        zero-filled.
        """
        if not members:
            return  # empty union — nothing to do

        first = members[0]
        m_ct = self._get_member_ctype(layout, first)
        m_ct_resolved = resolve_typedefs(m_ct, self._sema_ctx) if m_ct else None
        is_aggregate = (
            m_ct_resolved is not None
            and m_ct_resolved.kind in (TypeKind.STRUCT, TypeKind.UNION, TypeKind.ARRAY)
        )

        if not elems:
            # Empty initializer — zero-fill the first member.
            self._zero_fill_member(layout, first, m_ct, base_sym, is_ptr, src_line, src_col)
            return

        # Use the first element to initialize the first member.
        _desig, elem_init = elems[0]

        if is_aggregate and m_ct is not None:
            if not isinstance(elem_init, Initializer):
                # Wrap bare expression in an Initializer for the recursive call.
                elem_init = Initializer(
                    elements=[(None, elem_init)],
                    line=src_line, column=src_col,
                )
            ptr_ct = PointerType(kind=TypeKind.POINTER, pointee=m_ct)
            t_addr = self._new_temp_typed(ptr_ct)
            op_aom = "addr_of_member_ptr" if is_ptr else "addr_of_member"
            self.instructions.append(
                IRInstruction(
                    op=op_aom, result=t_addr,
                    operand1=base_sym, operand2=first,
                    result_type=ptr_ct,
                )
            )
            self._lower_initializer(m_ct, elem_init, t_addr, True)
        else:
            # Scalar first member.
            v = self._gen_expr(elem_init)
            meta = {"member_ctype": m_ct} if m_ct else None
            op_store = "store_member_ptr" if is_ptr else "store_member"
            self.instructions.append(
                IRInstruction(
                    op=op_store, result=v,
                    operand1=base_sym, operand2=first,
                    meta=meta,
                )
            )

    def _lower_designated_struct_init_new(
        self,
        ctype: CType,
        init: Initializer,
        base_sym: str,
        is_ptr: bool,
    ) -> None:
        """Lower a struct/union initializer with designators.

        Handles:
        - Member designators: ``.x = value``
        - Chained designators: ``.outer.inner = value``
        - Mixed designated/non-designated elements
        - Zero-fill for unspecified members

        Uses the same CType-driven dispatch as the sequential path:
        addr_of_member for aggregates, store_member for scalars.
        """
        ct = resolve_typedefs(ctype, self._sema_ctx)
        tag = getattr(ct, 'tag', None)
        if tag is None:
            raise IRGenError("_lower_designated_struct_init_new: cannot determine struct/union tag")

        prefix = 'union' if ct.kind == TypeKind.UNION else 'struct'
        layout_key = f"{prefix} {tag}"
        layouts = getattr(self._sema_ctx, 'layouts', {}) if self._sema_ctx else {}
        layout = layouts.get(layout_key) or layouts.get(tag)
        if layout is None:
            raise IRGenError(f"_lower_designated_struct_init_new: no layout for '{layout_key}'")

        members = list(getattr(layout, 'member_offsets', {}) or {})
        src_line = getattr(init, 'line', 0)
        src_col = getattr(init, 'column', 0)
        elems = init.elements or []

        # Build member → value mapping.
        # For chained designators on the same outer member, accumulate into a list.
        # Value types: Expression | Initializer | (Designator, Expression) for chained | list for multi-chained
        member_values: dict[str, Any] = {}
        cur_idx = 0  # sequential position for non-designated elements

        for desig, val in elems:
            if desig is not None:
                mname = self._resolve_designator_member(desig)
                if mname is not None and mname in layout.member_offsets:
                    if desig.next is not None:
                        # Chained designator (.outer.inner = value).
                        # Accumulate multiple chains for the same outer member.
                        existing = member_values.get(mname)
                        chain_entry = (desig.next, val)
                        if isinstance(existing, list):
                            existing.append(chain_entry)
                        elif isinstance(existing, tuple) and len(existing) == 2 and isinstance(existing[0], Designator):
                            member_values[mname] = [existing, chain_entry]
                        else:
                            member_values[mname] = chain_entry
                    else:
                        member_values[mname] = val
                    # Advance sequential position past this member.
                    try:
                        cur_idx = members.index(mname) + 1
                    except ValueError:
                        cur_idx = len(members)
            else:
                # Non-designated: assign to current sequential member.
                if cur_idx < len(members):
                    member_values[members[cur_idx]] = val
                    cur_idx += 1

        # Emit stores for all members: designated values or zero-fill.
        for m in members:
            val = member_values.get(m)
            m_ct = self._get_member_ctype(layout, m)

            if val is None:
                # Zero-fill unspecified member.
                self._zero_fill_member(layout, m, m_ct, base_sym, is_ptr, src_line, src_col)
                continue

            m_ct_resolved = resolve_typedefs(m_ct, self._sema_ctx) if m_ct else None
            is_aggregate = (
                m_ct_resolved is not None
                and m_ct_resolved.kind in (TypeKind.STRUCT, TypeKind.UNION, TypeKind.ARRAY)
            )

            if isinstance(val, list):
                # Multiple chained designators for the same outer member.
                # Build a synthetic Initializer with designated elements and recurse.
                self._emit_chained_designated_member(
                    layout, m, m_ct, val, base_sym, is_ptr, src_line, src_col,
                )
            elif isinstance(val, tuple) and len(val) == 2 and isinstance(val[0], Designator):
                # Single chained designator (.outer.inner = value).
                self._emit_chained_designated_member(
                    layout, m, m_ct, [val], base_sym, is_ptr, src_line, src_col,
                )
            elif is_aggregate and m_ct is not None:
                # Aggregate member with a direct value (Initializer or bare expr).
                ptr_ct = PointerType(kind=TypeKind.POINTER, pointee=m_ct)
                t_addr = self._new_temp_typed(ptr_ct)
                op_aom = "addr_of_member_ptr" if is_ptr else "addr_of_member"
                self.instructions.append(
                    IRInstruction(
                        op=op_aom, result=t_addr,
                        operand1=base_sym, operand2=m,
                        result_type=ptr_ct,
                    )
                )
                if not isinstance(val, Initializer):
                    val = Initializer(
                        elements=[(None, val)],
                        line=src_line, column=src_col,
                    )
                self._lower_initializer(m_ct, val, t_addr, True)
            else:
                # Scalar member: evaluate and store.
                v = self._gen_expr(val)
                meta = {"member_ctype": m_ct} if m_ct else None
                op_store = "store_member_ptr" if is_ptr else "store_member"
                self.instructions.append(
                    IRInstruction(
                        op=op_store, result=v,
                        operand1=base_sym, operand2=m,
                        meta=meta,
                    )
                )

    def _emit_chained_designated_member(
        self,
        layout,
        member: str,
        m_ct: Optional[CType],
        chains: list,
        base_sym: str,
        is_ptr: bool,
        src_line: int,
        src_col: int,
    ) -> None:
        """Emit IR for chained designator(s) targeting a nested member.

        ``chains`` is a list of ``(next_designator, value)`` tuples.
        Gets the member address, builds a synthetic Initializer with
        designated elements, and recurses via ``_lower_initializer``.
        """
        if m_ct is None:
            return
        ptr_ct = PointerType(kind=TypeKind.POINTER, pointee=m_ct)
        t_addr = self._new_temp_typed(ptr_ct)
        op_aom = "addr_of_member_ptr" if is_ptr else "addr_of_member"
        self.instructions.append(
            IRInstruction(
                op=op_aom, result=t_addr,
                operand1=base_sym, operand2=member,
                result_type=ptr_ct,
            )
        )
        # Build a synthetic Initializer with the chained designator elements.
        synth_elements = [(sub_desig, sub_val) for sub_desig, sub_val in chains]
        synth_init = Initializer(
            elements=synth_elements,
            line=src_line, column=src_col,
        )
        self._lower_initializer(m_ct, synth_init, t_addr, True)

    def _zero_fill_member(
        self,
        layout,
        member: str,
        m_ct: Optional[CType],
        base_sym: str,
        is_ptr: bool,
        src_line: int,
        src_col: int,
    ) -> None:
        """Zero-fill a single struct member.

        For aggregate members (struct/union/array), gets the member address
        and recurses with an empty Initializer.  For scalar members, emits
        a store of $0.
        """
        m_ct_resolved = resolve_typedefs(m_ct, self._sema_ctx) if m_ct else None
        is_aggregate = (
            m_ct_resolved is not None
            and m_ct_resolved.kind in (TypeKind.STRUCT, TypeKind.UNION, TypeKind.ARRAY)
        )

        if is_aggregate and m_ct is not None:
            # Zero-fill aggregate: get address, recurse with empty Initializer.
            ptr_ct = PointerType(kind=TypeKind.POINTER, pointee=m_ct)
            t_addr = self._new_temp_typed(ptr_ct)
            op_aom = "addr_of_member_ptr" if is_ptr else "addr_of_member"
            self.instructions.append(
                IRInstruction(
                    op=op_aom, result=t_addr,
                    operand1=base_sym, operand2=member,
                    result_type=ptr_ct,
                )
            )
            zero_init = Initializer(elements=[], line=src_line, column=src_col)
            self._lower_initializer(m_ct, zero_init, t_addr, True)
        else:
            # Scalar: emit store of zero.
            zero_expr = IntLiteral(
                value=0, is_hex=False, is_octal=False,
                line=src_line, column=src_col,
            )
            v = self._gen_expr(zero_expr)
            meta = {"member_ctype": m_ct} if m_ct else None
            op_store = "store_member_ptr" if is_ptr else "store_member"
            self.instructions.append(
                IRInstruction(
                    op=op_store, result=v,
                    operand1=base_sym, operand2=member,
                    meta=meta,
                )
            )

    def _new_label(self, prefix: str = ".L") -> str:
        l = f"{prefix}{self.label_counter}"
        self.label_counter += 1
        return l

    def _push_scope(self):
        self._scope_stack.append({})

    def _pop_scope(self):
        if self._scope_stack:
            self._scope_stack.pop()

    def _declare_scoped(self, name: str) -> str:
        """Register a local variable in the current scope. Returns the IR symbol.
        If the name shadows an outer scope, generates a unique alias."""
        # Check if name already exists in any outer scope
        for scope in self._scope_stack:
            if name in scope:
                # Shadow: create unique alias
                self._shadow_counter += 1
                alias = f"@{name}__shadow{self._shadow_counter}"
                if self._scope_stack:
                    self._scope_stack[-1][name] = alias
                return alias
        # No shadow: use plain @name
        sym = f"@{name}"
        if self._scope_stack:
            self._scope_stack[-1][name] = sym
        return sym

    def _resolve_name(self, name: str) -> str:
        """Resolve a variable name to its IR symbol, respecting scope."""
        for scope in reversed(self._scope_stack):
            if name in scope:
                return scope[name]
        # Check function-local static variables.
        m = getattr(self, "_local_static_syms", {})
        if name in m:
            return f"@{m[name]}"
        return f"@{name}"

    def _is_struct_or_union_type(self, base: object) -> bool:
        if not isinstance(base, str):
            return False
        b = base.strip()
        # Pointer types are never struct/union values themselves.
        if "*" in b:
            return False
        if b.startswith("struct ") or b.startswith("union "):
            return True
        # Resolve typedef: a typedef name may refer to a struct/union.
        if self._sema_ctx is not None:
            seen = set()
            name = b
            while name and name not in seen:
                seen.add(name)
                td = getattr(self._sema_ctx, "typedefs", {}).get(name)
                if td is None:
                    break
                tb = getattr(td, "base", None)
                if isinstance(tb, str):
                    tb = tb.strip()
                    if tb.startswith("struct ") or tb.startswith("union "):
                        return True
                    name = tb
                else:
                    break
            # Also check if the name exists as a layout key (e.g. registered
            # via _register_struct with the typedef name itself).
            layouts = getattr(self._sema_ctx, "layouts", None) or getattr(self._sema_ctx, "_layouts", {})
            if b in layouts:
                return True
        return False

    def _has_any_designator(self, init: Initializer) -> bool:
        """Return True if any element in the initializer has a Designator."""
        for desig, _val in (init.elements or []):
            if desig is not None:
                return True
        return False

    def _resolve_designator_member(self, desig: Designator) -> str | None:
        """Return the top-level member name from a member designator."""
        if desig.member is not None:
            return desig.member
        return None

    def _resolve_designator_index(self, desig: Designator) -> int | None:
        """Return the integer index from an array designator, or None."""
        if desig.index is not None:
            try:
                return _eval_const_int_expr(desig.index)
            except Exception:
                return None
        return None

    # Functions

    def _gen_function(self, fn: FunctionDecl) -> None:
        self._fn_name = fn.name
        # Best-effort: function return type string for ABI-sensitive returns.
        # FunctionDecl uses `.return_type` in this codebase.
        try:
            rt0 = getattr(fn, "return_type", "")
            rt_base = getattr(rt0, "base", rt0)
            if getattr(rt0, "is_pointer", False):
                # Pointer return type: record as "base*" so codegen doesn't
                # apply narrow-type return value extension (e.g. char -> movsbl).
                self._fn_ret_type = str(rt_base) + "*"
            else:
                self._fn_ret_type = self._canon_int_type(str(rt_base))
        except Exception:
            self._fn_ret_type = ""
        # Preserve internal linkage for `static` functions: do not emit them as
        # global symbols, otherwise the linker may treat parameter names as
        # unresolved externs if they are mis-lowered.
        # Codegen understands the label suffix "@static".
        fn_label = fn.name
        try:
            if getattr(fn, "storage_class", None) == "static":
                fn_label = f"{fn.name}@static"
        except Exception:
            pass

        self.instructions.append(IRInstruction(op="func_begin", label=fn_label))
        # Record function return type for codegen (used by `ret`).
        if self._fn_ret_type:
            self.instructions.append(IRInstruction(op="func_ret", operand1=self._fn_ret_type))
        # reset per-function array set
        self._local_arrays = set()
        # Track declared types of locals/params for signedness decisions.
        #
        # NOTE: _var_types CANNOT be removed yet (task 7.2 deferred).
        # Codegen's _var_types (task 7.1, also deferred) is populated by
        # pre-scanning IR decl/param instructions, which carry the type
        # strings that this dictionary produces.  Since codegen still
        # depends on _var_types for all function-local type lookups
        # (TypedSymbolTable scopes are popped after IR generation, leaving
        # only global-scope entries), the IR generator must continue to
        # dual-populate both _sym_table and _var_types.
        #
        # To remove this dictionary, the architecture must first change so
        # that TypedSymbolTable preserves per-function scopes across the
        # IR-gen -> codegen boundary (see codegen.py task 7.1 comment).
        self._var_types: dict[str, str] = {}
        # Track volatile-qualified variables (IR symbols like @x).
        self._var_volatile: set[str] = set()
        # Function-local static storage (lowered to global symbols).
        # Maps source name -> global symbol name (without leading '@').
        self._local_static_syms: dict[str, str] = {}
        def _ty_str(t) -> str:
            # Encode pointer-ness in the type string so codegen doesn't
            # accidentally spill pointer args using 8/16/32-bit stores.
            base = str(getattr(t, "base", ""))
            try:
                if isinstance(base, str) and (base.strip().startswith("struct ") or base.strip().startswith("union ")):
                    base = base.strip()
            except Exception:
                pass
            plevel = getattr(t, "pointer_level", 0) or 0
            if plevel > 0:
                return base + "*" * plevel
            if getattr(t, "is_pointer", False):
                return f"{base}*"
            return base

        # params are treated as locals; codegen will map them from ABI regs
        self._scope_stack = []
        self._push_scope()  # function-level scope
        if self._sym_table:
            self._sym_table.push_scope()
        for p in fn.parameters:
            ty_s = _ty_str(p.type)
            self._var_types[f"@{p.name}"] = ty_s
            self._scope_stack[-1][p.name] = f"@{p.name}"
            self.instructions.append(IRInstruction(op="param", result=f"@{p.name}", operand1=ty_s))
            # Insert parameter CType into symbol table (dual-populate).
            if self._sym_table:
                ctype = ast_type_to_ctype_resolved(p.type, self._sema_ctx)
                self._sym_table.insert(f"@{p.name}", ctype)
            # Track volatile-qualified parameters.
            if getattr(p.type, "is_volatile", False):
                self._var_volatile.add(f"@{p.name}")
        self._gen_stmt(fn.body)
        self._pop_scope()
        if self._sym_table:
            self._sym_table.pop_scope(func_name=fn.name)
        # Ensure a return exists
        self.instructions.append(IRInstruction(op="ret", operand1="$0"))
        self.instructions.append(IRInstruction(op="func_end", label=fn.name))
        self._fn_name = None
        self._fn_ret_type = None

    def _current_function_name(self) -> str:
        return str(getattr(self, "_fn_name", ""))

    def _ensure_local_static_aliases(self) -> None:
        """Best-effort aliasing of local static identifiers.

        Local statics are lowered to unique global symbols, but the rest of the
        IR generator expects identifiers to lower to `@name`. This helper makes
        sure we have a mapping ready for the current function.
        """

        if not hasattr(self, "_local_static_syms"):
            self._local_static_syms = {}

    # Statements

    def _gen_stmt(self, stmt: Statement) -> None:
        if isinstance(stmt, CompoundStmt):
            self._push_scope()
            for item in stmt.statements:
                if isinstance(item, Declaration):
                    # Register in scope for variable shadowing
                    if getattr(item, "storage_class", None) != "static":
                        self._declare_scoped(item.name)

                    # Resolve typedef array types: if the base type is a
                    # typedef with array dimensions (e.g. typedef int arr_t[5]),
                    # propagate array_size/array_dims onto the Declaration so
                    # downstream array handling works correctly.
                    if (getattr(item, "array_size", None) is None
                            and self._sema_ctx is not None):
                        _td_base = getattr(item.type, "base", "")
                        if isinstance(_td_base, str) and _td_base:
                            _td_dict = getattr(self._sema_ctx, "typedefs", None)
                            if isinstance(_td_dict, dict):
                                _td_ty = _td_dict.get(_td_base)
                            else:
                                _td_ty = None
                            if _td_ty is not None:
                                _td_dims = getattr(_td_ty, "array_dims", None)
                                if _td_dims:
                                    item.array_size = getattr(_td_ty, "array_size", _td_dims[0])
                                    item.array_dims = list(_td_dims)

                    # Track volatile-qualified local variables.
                    try:
                        if getattr(item.type, "is_volatile", False):
                            self._var_volatile.add(self._resolve_name(item.name))
                    except Exception:
                        pass

                    # Local static variables: lower to a unique global symbol so state persists.
                    if getattr(item, "storage_class", None) == "static":
                        self._ensure_local_static_aliases()
                        gname = f"__local_static_{self._current_function_name()}_{item.name}_{self.label_counter}"
                        self.label_counter += 1
                        self._local_static_syms[item.name] = gname

                        # Define storage once, with constant initializer if present.
                        if getattr(item, "initializer", None) is None:
                            arr_sz = getattr(item, "array_size", None)
                            if arr_sz is not None:
                                # Local static array: emit as BSS with correct total size.
                                elem_sz = self._sizeof(item.type)
                                total = int(arr_sz) * elem_sz
                                self.instructions.append(IRInstruction(
                                    op="gdecl", result=f"@{gname}",
                                    operand1=f"array({item.type.base},${arr_sz})",
                                    label="static",
                                    meta={"size": total},
                                ))
                            else:
                                self.instructions.append(IRInstruction(op="gdef", result=f"@{gname}", operand1=item.type.base, operand2="$0", label="static"))
                        else:
                            # Try aggregate blob first (arrays, structs).
                            blob = self._const_initializer_blob(item)
                            if blob is not None:
                                self.instructions.append(
                                    IRInstruction(op="gdef_blob", result=f"@{gname}", operand1=item.type.base, operand2=blob, label="static")
                                )
                            else:
                                imm = self._const_initializer_imm(item.initializer)
                                ptr = self._const_initializer_ptr(item.initializer)
                                # Float scalar
                                if isinstance(item.initializer, FloatLiteral):
                                    suffix = getattr(item.initializer, 'suffix', '')
                                    fp_type = "long double" if suffix in ('l','L') else "float" if suffix in ('f','F') else "double"
                                    self.instructions.append(
                                        IRInstruction(op="gdef_float", result=f"@{gname}", operand1=str(item.initializer.value), label="static", meta={"fp_type": fp_type})
                                    )
                                elif imm is not None or ptr is not None:
                                    self.instructions.append(
                                        IRInstruction(op="gdef", result=f"@{gname}", operand1=item.type.base, operand2=imm if imm is not None else ptr, label="static")
                                    )
                                else:
                                    # Try struct member-by-member init (handles function pointers, symbols).
                                    _saved_name = item.name
                                    item.name = gname  # _try_struct_member_init uses decl.name
                                    if self._try_struct_member_init(item, "static"):
                                        item.name = _saved_name
                                    else:
                                        item.name = _saved_name
                                        raise IRGenError(
                                            f"unsupported local static initializer for {item.name}: only integer/char constants and string-literal pointers supported"
                                        )

                        # Record type for the lowered global symbol.
                        arr_sz = getattr(item, "array_size", None)
                        if arr_sz is not None:
                            # Array: record as array type so codegen emits leaq (address) not movslq (value).
                            self._var_types[f"@{gname}"] = f"array({item.type.base},${arr_sz})"
                        else:
                            self._var_types[f"@{gname}"] = str(item.type.base)
                        # Insert local static CType into symbol table (dual-populate).
                        self._insert_decl_ctype(f"@{gname}", item)
                        # Track volatile for local statics.
                        if getattr(item.type, "is_volatile", False):
                            self._var_volatile.add(f"@{gname}")

                        # If initializer exists, we already applied it at global init time.
                        # Skip normal local decl/init lowering.
                        continue

                    # If this is an array with known size, encode element count in operand1.
                    # Also support C89: `char s[] = "..."` (size inferred from string literal).
                    op1 = None
                    if getattr(item, "array_size", None) is not None:
                        elem_ty = item.type.base
                        # Resolve typedef element type to underlying type name
                        # so codegen knows the correct element size.
                        if isinstance(elem_ty, str) and self._sema_ctx is not None:
                            _resolved_elem = self._resolve_elem_type(elem_ty.strip())
                            if _resolved_elem:
                                elem_ty = _resolved_elem
                        if getattr(item.type, "is_pointer", False):
                            elem_ty = f"{elem_ty}*"
                        # For multi-dimensional arrays, compute total element
                        # count as the product of all dimensions so the backing
                        # store is large enough.
                        total_elems = int(item.array_size)
                        try:
                            ad = getattr(item, "array_dims", None)
                            if isinstance(ad, list) and len(ad) >= 2:
                                prod = 1
                                for d in ad:
                                    if isinstance(d, int):
                                        prod *= d
                                if prod > total_elems:
                                    total_elems = prod
                        except Exception:
                            pass
                        op1 = f"array({elem_ty},${total_elems})"
                    else:
                        # Infer `char[]` size from string-literal initializer.
                        if item.type.base in {"char", "unsigned char"} and item.initializer is not None:
                            inits0 = self._const_initializer_list(item.initializer)
                            if inits0 is not None and len(inits0) == 1 and isinstance(inits0[0], StringLiteral):
                                s0 = inits0[0].value
                                op1 = f"array(char,${len(s0) + 1})"

                    # Emit decl and record type info.
                    # Priority:
                    # 1) arrays (known or inferred)
                    # 2) struct/union scalar objects
                    # 3) scalars (incl pointers)
                    #
                    # NOTE: we must infer `T[]` length *before* choosing the
                    # array vs struct branch, otherwise `int a[] = {...}` will
                    # never become an array.

                    # Infer `T[]` element count from brace initializer.
                    # e.g. `int a[] = {1,2,3};`
                    if op1 is None and getattr(item, "array_size", None) is None and item.initializer is not None:
                        inits0 = self._const_initializer_list(item.initializer)
                        if inits0 is not None and isinstance(item.type.base, str) and item.type.base in {"int", "char", "unsigned char"}:
                            if all(isinstance(e, (IntLiteral, CharLiteral, UnaryOp)) for e in inits0):
                                n0 = len(inits0)
                                op1 = f"array({item.type.base},${n0})"
                                try:
                                    item.array_size = n0
                                except Exception:
                                    pass

                    # C89: allow omitted first dimension in 2D arrays with known
                    # inner dimension, inferred from a nested initializer list.
                    # Example: `char a[][4] = { {..}, {..} };` => dims [2, 4].
                    if op1 is None and getattr(item, "array_size", None) is None and item.initializer is not None:
                        try:
                            ad = getattr(item, "array_dims", None)
                        except Exception:
                            ad = None
                        # Parser stores dims outer->inner; for `[][4]` it's [None, 4].
                        if isinstance(ad, list) and len(ad) >= 2 and ad[0] is None and isinstance(ad[1], int):
                            inits0 = self._const_initializer_list(item.initializer)
                            from pycc.ast_nodes import Initializer as ASTInit

                            if inits0 is not None and any(isinstance(x, ASTInit) for x in inits0):
                                # Each top-level element corresponds to a row.
                                outer_n = len(inits0)
                                item.array_size = int(outer_n)
                                try:
                                    item.array_dims = [int(outer_n), int(ad[1])] + [int(x) if isinstance(x, int) else None for x in ad[2:]]
                                except Exception:
                                    pass
                                op1 = f"array({item.type.base},${int(outer_n) * int(ad[1])})"
                                try:
                                    self._local_array_dims[item.name] = list(getattr(item, "array_dims", []) or [])
                                except Exception:
                                    pass

                    # Multi-dimensional arrays: we only model a 1D backing store
                    # plus optional dims metadata (used for pointer-to-row decay
                    # and 2D initializer flattening).

                    # If this is an array with known/inferred size, record it
                    # as an array type even when element type is struct/union.
                    if op1 is not None:
                        self.instructions.append(IRInstruction(op="decl", result=self._resolve_name(item.name), operand1=op1))
                        self._local_arrays.add(item.name)
                        self._var_types[self._resolve_name(item.name)] = str(op1)
                        # Insert array CType into symbol table (dual-populate).
                        self._insert_decl_ctype(self._resolve_name(item.name), item)
                        # Record multi-dimensional array dims for upcoming
                        # pointer-to-row decay/scaling support.
                        try:
                            ad = getattr(item, "array_dims", None)
                            if isinstance(ad, list) and len(ad) >= 2 and all(isinstance(d, int) for d in ad if d is not None):
                                self._local_array_dims[item.name] = ad
                        except Exception:
                            pass
                    elif not getattr(item.type, "is_pointer", False) and self._is_struct_or_union_type(item.type.base):
                        decl_op1 = str(item.type.base)
                        self.instructions.append(IRInstruction(op="decl", result=self._resolve_name(item.name), operand1=decl_op1))
                        self._var_types[self._resolve_name(item.name)] = decl_op1
                        # Insert struct/union CType into symbol table (dual-populate).
                        self._insert_decl_ctype(self._resolve_name(item.name), item)
                    else:
                        # Infer `T[]` element count from brace initializer.
                        # e.g. `int a[] = {1,2,3};`
                        if op1 is None:
                            # Preserve explicit signedness for narrow integer types.
                            # Parser keeps `base` as "char" and stores qualifiers
                            # in Type flags.
                            decl_op1 = item.type.base
                            try:
                                if decl_op1 == "char":
                                    if getattr(item.type, "is_signed", False):
                                        decl_op1 = "signed char"
                                    elif getattr(item.type, "is_unsigned", False):
                                        decl_op1 = "unsigned char"
                            except Exception:
                                pass
                            if getattr(item.type, "is_pointer", False):
                                decl_base = str(decl_op1).strip()
                                plevel = int(getattr(item.type, "pointer_level", 1) or 1)
                                stars = "*" * plevel
                                if decl_base.startswith("struct ") or decl_base.startswith("union "):
                                    decl_op1 = f"{decl_base}{stars}"
                                else:
                                    decl_op1 = f"{decl_op1}{stars}"
                            self.instructions.append(IRInstruction(op="decl", result=self._resolve_name(item.name), operand1=decl_op1))
                            self._var_types[self._resolve_name(item.name)] = str(decl_op1)
                            # Insert scalar CType into symbol table (dual-populate).
                            self._insert_decl_ctype(self._resolve_name(item.name), item)
                    # If this is a pointer variable, record its declared pointee
                    # type so pointer arithmetic can scale correctly.
                    try:
                        if getattr(item.type, "is_pointer", False) and item.name not in self._local_arrays:
                            base = str(getattr(item.type, "base", "")).strip()
                            if base:
                                self._var_types[self._resolve_name(item.name)] = f"{base}*"
                    except Exception:
                        pass
                    # ── Unified initializer lowering ──────────────────
                    # Build CType from the Declaration and delegate to
                    # _lower_initializer for all initializer forms.
                    if item.initializer is not None:
                        base_sym = self._resolve_name(item.name)
                        # Determine if this is truly an array declaration.
                        # The ground truth is _local_arrays membership: if the
                        # decl was emitted as array(...), the init must use
                        # array-style stores.  This covers cases like
                        # `const char* s = "abc"` where the parser sets
                        # is_pointer=True but the inferred-size logic above
                        # declared it as array(char,$4).
                        is_array = item.name in self._local_arrays
                        if is_array:
                            # Array: construct CType from the element base type
                            # (not the full pointer type).  The decl was emitted
                            # as array(elem_type,$N) where elem_type is
                            # item.type.base, so we must match that.
                            arr_sz = getattr(item, "array_size", None)
                            # Build element CType from the base type string,
                            # ignoring pointer wrapping.  For `char *a[3]`,
                            # the element is `char*`; for `const char* s = "abc"`,
                            # the element is `char`.
                            if getattr(item.type, 'is_pointer', False) and arr_sz is None:
                                # Inferred-size pointer case: element is the
                                # bare base type (e.g. char), not char*.
                                elem_ctype = _str_to_ctype(str(item.type.base).strip())
                            else:
                                elem_ctype = ast_type_to_ctype_resolved(item.type, self._sema_ctx)
                            # Determine the effective array size.  For inferred
                            # sizes (e.g. `char s[] = "hi"`) item.array_size
                            # may still be None — extract from _var_types.
                            eff_sz = int(arr_sz) if arr_sz is not None else None
                            if eff_sz is None:
                                # Try to extract from the recorded var type
                                # string like "array(char,$3)".
                                vt = self._var_types.get(base_sym, "")
                                if isinstance(vt, str) and vt.startswith("array("):
                                    try:
                                        _dollar = vt.rfind("$")
                                        _paren = vt.rfind(")")
                                        if _dollar >= 0 and _paren > _dollar:
                                            eff_sz = int(vt[_dollar + 1:_paren])
                                    except (ValueError, IndexError):
                                        pass
                            ad = getattr(item, "array_dims", None)
                            if isinstance(ad, list) and len(ad) >= 2:
                                # Multi-dimensional array: flat backing store.
                                total = 1
                                for d in ad:
                                    if isinstance(d, int):
                                        total *= d
                                decl_ctype = CArrayType(
                                    kind=TypeKind.ARRAY,
                                    element=elem_ctype,
                                    size=total,
                                )
                                flat_init = self._flatten_multidim_init(
                                    item.initializer, ad, item.line, item.column
                                )
                                self._lower_initializer(decl_ctype, flat_init, base_sym, is_ptr=False)
                            else:
                                decl_ctype = CArrayType(
                                    kind=TypeKind.ARRAY,
                                    element=elem_ctype,
                                    size=eff_sz,
                                )
                                self._lower_initializer(decl_ctype, item.initializer, base_sym, is_ptr=False)
                        else:
                            # Scalar or struct/union (non-array).
                            base_ctype = ast_type_to_ctype_resolved(item.type, self._sema_ctx)
                            self._lower_initializer(base_ctype, item.initializer, base_sym, is_ptr=False)
                            # Propagate pointer-to-row step metadata from the
                            # decay temp into the local symbol, so later pointer
                            # arithmetic (e.g. p+1) can scale correctly.
                            # This only applies to scalar pointer init like
                            # `int (*p)[4] = a;` where _gen_expr produces a
                            # temp with step metadata.
                            try:
                                # Peek at the last instruction to find the
                                # source operand for step propagation.
                                last_instr = self.instructions[-1] if self.instructions else None
                                if last_instr and last_instr.op == "mov" and isinstance(last_instr.operand1, str):
                                    src_step = getattr(self, "_ptr_step_bytes", {}).get(last_instr.operand1)
                                    if src_step is not None:
                                        self._ptr_step_bytes[base_sym] = src_step
                            except Exception:
                                pass
                else:
                    self._gen_stmt(item)
            self._pop_scope()
            return

        if isinstance(stmt, ExpressionStmt):
            if stmt.expression is not None:
                self._gen_expr(stmt.expression)
            return

        if isinstance(stmt, IfStmt):
            else_lbl = self._new_label(".Lelse")
            end_lbl = self._new_label(".Lendif")
            cond = self._gen_expr(stmt.condition)
            self.instructions.append(IRInstruction(op="jz", operand1=cond, label=else_lbl))
            self._gen_stmt(stmt.then_stmt)
            self.instructions.append(IRInstruction(op="jmp", label=end_lbl))
            self.instructions.append(IRInstruction(op="label", label=else_lbl))
            if stmt.else_stmt is not None:
                self._gen_stmt(stmt.else_stmt)
            self.instructions.append(IRInstruction(op="label", label=end_lbl))
            return

        if isinstance(stmt, WhileStmt):
            start = self._new_label(".Lwhile")
            end = self._new_label(".Lendwhile")
            self._break_stack.append(end)
            self._continue_stack.append(start)
            self.instructions.append(IRInstruction(op="label", label=start))
            cond = self._gen_expr(stmt.condition)
            self.instructions.append(IRInstruction(op="jz", operand1=cond, label=end))
            self._gen_stmt(stmt.body)
            self.instructions.append(IRInstruction(op="jmp", label=start))
            self.instructions.append(IRInstruction(op="label", label=end))
            self._break_stack.pop()
            self._continue_stack.pop()
            return

        if isinstance(stmt, DoWhileStmt):
            start = self._new_label(".Ldo")
            end = self._new_label(".Lenddo")
            self._break_stack.append(end)
            self._continue_stack.append(start)
            self.instructions.append(IRInstruction(op="label", label=start))
            self._gen_stmt(stmt.body)
            cond = self._gen_expr(stmt.condition)
            self.instructions.append(IRInstruction(op="jnz", operand1=cond, label=start))
            self.instructions.append(IRInstruction(op="label", label=end))
            self._break_stack.pop()
            self._continue_stack.pop()
            return

        if isinstance(stmt, ForStmt):
            start = self._new_label(".Lfor")
            end = self._new_label(".Lendfor")
            cont = self._new_label(".Lforcont")
            self._break_stack.append(end)
            self._continue_stack.append(cont)
            if isinstance(stmt.init, Declaration):
                self.instructions.append(IRInstruction(op="decl", result=f"@{stmt.init.name}"))
                if stmt.init.initializer is not None:
                    v = self._gen_expr(stmt.init.initializer)
                    self.instructions.append(IRInstruction(op="mov", result=f"@{stmt.init.name}", operand1=v))
            elif stmt.init is not None:
                self._gen_expr(stmt.init)
            self.instructions.append(IRInstruction(op="label", label=start))
            if stmt.condition is not None:
                c = self._gen_expr(stmt.condition)
                self.instructions.append(IRInstruction(op="jz", operand1=c, label=end))
            if stmt.body is not None:
                self._gen_stmt(stmt.body)
            self.instructions.append(IRInstruction(op="label", label=cont))
            if stmt.update is not None:
                self._gen_expr(stmt.update)
            self.instructions.append(IRInstruction(op="jmp", label=start))
            self.instructions.append(IRInstruction(op="label", label=end))
            self._break_stack.pop()
            self._continue_stack.pop()
            return

        if isinstance(stmt, SwitchStmt):
            # Lower as a chain of compares/jumps (no jump table).
            #
            # Key property: fallthrough must work. That means the *body* of the switch
            # must be emitted as one linear statement stream where `case`/`default`
            # are just labels, not isolated sub-statements.
            end = self._new_label(".Lendswitch")
            self._break_stack.append(end)

            sw = self._gen_expr(stmt.expression)

            # Flatten the switch body into a linear list of items.
            # The parser currently models `case ...: stmt` as `CaseStmt(value, statement)`.
            # We treat that as: [case-label, ...flatten(stmt)...].
            flat: List[Union[Statement, Declaration]] = []

            def _flatten(s: Statement) -> None:
                if isinstance(s, CompoundStmt):
                    for it in s.statements:
                        flat.append(it)
                    return
                flat.append(s)

            _flatten(stmt.body)

            # Switch bodies are normally a CompoundStmt. If it's not, we still want
            # local declarations like `switch(x) int r=0;` to work via normal lowering.
            # (This is also the place to ensure we don't treat local decls as globals.)
            if not isinstance(stmt.body, CompoundStmt):
                # Emit the body as-is after dispatch (rare in well-formed C).
                pass

            # Map labels for each case/default in the flattened stream.
            case_entries: List[tuple[CaseStmt, str]] = []
            default_lbl: Optional[str] = None
            seen_case_values: set[int] = set()
            for it in flat:
                if isinstance(it, CaseStmt):
                    # C89 subset: case labels must be integer constant expressions.
                    try:
                        cvi = _eval_const_int_expr(it.value, getattr(self, "_enum_constants", None))
                    except IRGenError:
                        cvi = self._const_expr_to_int(it.value)
                        if cvi is None:
                            raise IRGenError("switch case value must be an integer constant expression")
                    if cvi in seen_case_values:
                        raise IRGenError(f"duplicate case value in switch: {cvi}")
                    seen_case_values.add(cvi)
                    case_entries.append((it, self._new_label(".Lcase")))
                elif isinstance(it, DefaultStmt):
                    if default_lbl is None:
                        default_lbl = self._new_label(".Ldefault")
                    else:
                        raise IRGenError("multiple default labels in switch")

            dispatch_default = default_lbl if default_lbl is not None else end

            # Dispatch chain: if (sw == cv) goto case_label
            for c, lbl in case_entries:
                cv = self._gen_expr(c.value)
                t = self._new_temp()
                self.instructions.append(IRInstruction(op="binop", result=t, operand1=sw, operand2=cv, label="=="))
                self.instructions.append(IRInstruction(op="jnz", operand1=t, label=lbl))
            self.instructions.append(IRInstruction(op="jmp", label=dispatch_default))

            # Emit the linear body stream.
            # - Declarations inside the switch compound allocate locals as usual.
            # - `case`/`default` emit labels, then continue emitting subsequent statements.
            case_label_by_id = {id(c): lbl for (c, lbl) in case_entries}

            for it in flat:
                if isinstance(it, CaseStmt):
                    lbl = case_label_by_id.get(id(it))
                    if lbl is None:
                        # Shouldn't happen, but keep lowering robust.
                        lbl = self._new_label(".Lcase")
                    self.instructions.append(IRInstruction(op="label", label=lbl))
                    # Emit the statement that syntactically follows the label.
                    self._gen_stmt(it.statement)
                    continue

                if isinstance(it, DefaultStmt):
                    # default label
                    if default_lbl is None:
                        default_lbl = self._new_label(".Ldefault")
                    self.instructions.append(IRInstruction(op="label", label=default_lbl))
                    self._gen_stmt(it.statement)
                    continue

                self._gen_stmt(it)

            self.instructions.append(IRInstruction(op="label", label=end))
            self._break_stack.pop()
            return

        if isinstance(stmt, CaseStmt):
            # Normally handled inside SwitchStmt lowering.
            self._gen_stmt(stmt.statement)
            return

        if isinstance(stmt, DefaultStmt):
            # Normally handled inside SwitchStmt lowering.
            self._gen_stmt(stmt.statement)
            return

        if isinstance(stmt, LabelStmt):
            # C labels are function-scoped. Use function name + label name
            # to ensure uniqueness across functions in the same TU.
            fn = getattr(self, "_fn_name", "") or ""
            lbl = f".Luser_{fn}_{stmt.name}"
            self.instructions.append(IRInstruction(op="label", label=lbl))
            self._gen_stmt(stmt.statement)
            return

        if isinstance(stmt, GotoStmt):
            fn = getattr(self, "_fn_name", "") or ""
            self.instructions.append(IRInstruction(op="jmp", label=f".Luser_{fn}_{stmt.label}"))
            return

        if isinstance(stmt, BreakStmt):
            if self._break_stack:
                self.instructions.append(IRInstruction(op="jmp", label=self._break_stack[-1]))
            return

        if isinstance(stmt, ContinueStmt):
            if self._continue_stack:
                self.instructions.append(IRInstruction(op="jmp", label=self._continue_stack[-1]))
            return

        if isinstance(stmt, ReturnStmt):
            if stmt.value is None:
                self.instructions.append(IRInstruction(op="ret", operand1="$0"))
            else:
                v = self._gen_expr(stmt.value)

                # Best-effort: annotate return-value temp with the function's
                # declared return type so codegen can apply ABI-required
                # sign/zero extension for narrow integer returns.
                try:
                    if isinstance(v, str) and v.startswith("%") and hasattr(self, "_fn_ret_type") and self._fn_ret_type:
                        rt = str(self._fn_ret_type)
                        rtn = rt.strip().lower()
                        if rtn in {"short", "unsigned short", "signed short", "char", "unsigned char", "signed char"}:
                            self._var_types[v] = rt
                except Exception:
                    pass
                self.instructions.append(IRInstruction(op="ret", operand1=v))
            return

        # ignore unsupported statements

    # Expressions

    def _gen_expr(self, expr: Expression) -> str:
        if isinstance(expr, IntLiteral):
            return f"${expr.value}"
        if isinstance(expr, FloatLiteral):
            suffix = getattr(expr, 'suffix', '')
            if suffix in ('l', 'L'):
                fp_type = "long double"
                _fp_ctype = FloatType(kind=TypeKind.DOUBLE)  # best approx
            elif suffix in ('f', 'F'):
                fp_type = "float"
                _fp_ctype = FloatType(kind=TypeKind.FLOAT)
            else:
                fp_type = "double"
                _fp_ctype = FloatType(kind=TypeKind.DOUBLE)
            t = self._new_temp_typed(_fp_ctype)
            self.instructions.append(IRInstruction(
                op="fmov", result=t, operand1=str(expr.value),
                meta={"fp_type": fp_type}
            ))
            self._var_types[t] = fp_type
            return t
        if isinstance(expr, CharLiteral):
            # In C, character constants have type int.
            # Our AST stores the raw single-character string.
            return f"${ord(expr.value)}"
        if isinstance(expr, StringLiteral):
            # String literal: type is char* (pointer to char).
            _str_ctype = PointerType(kind=TypeKind.POINTER,
                                     pointee=IntegerType(kind=TypeKind.CHAR))
            t = self._new_temp_typed(_str_ctype)
            # encode string in IR as str_const with result temp
            self.instructions.append(IRInstruction(op="str_const", result=t, operand1=expr.value))
            # Record that this temp is a pointer (char*).
            self._var_types[t] = "char*"
            return t
        if isinstance(expr, SizeOf):
            if expr.type is not None:
                return f"${self._sizeof(expr.type)}"
            # sizeof(expression): handle a few common expression shapes.
            op = expr.operand
            if op is None:
                return "$8"

            # Reject sizeof(function-designator) conservatively. We only apply
            # this to the simple `sizeof(f)` form where `f` is an identifier
            # and it is *not* known to be a local/global object.
            try:
                from pycc.ast_nodes import Identifier as ASTIdentifier

                if isinstance(op, ASTIdentifier):
                    sym = f"@{op.name}"
                    ty_s = getattr(self, "_var_types", {}).get(sym)
                    if isinstance(ty_s, str):
                        # If we already know it's an object, it's fine.
                        pass
                    else:
                        # Fall back to semantic context for globals.
                        gty = None
                        if getattr(self, "_sema_ctx", None) is not None:
                            gty = getattr(self._sema_ctx, "global_decl_types", {}).get(op.name)

                        # If it's a global object, it's fine.
                        if gty is not None:
                            pass
                        else:
                            # As a final step, if this identifier is the name of a
                            # function (known in sema function_sigs), reject.
                            fs = None
                            if getattr(self, "_sema_ctx", None) is not None:
                                fs = getattr(self._sema_ctx, "function_sigs", {})
                            if isinstance(fs, dict) and op.name in fs:
                                raise IRGenError("invalid application of sizeof to function type")
            except IRGenError:
                raise
            except Exception:
                pass
            # If semantics has already attached a type to the operand
            # expression, use it.
            try:
                op_ty = getattr(op, "type", None)
                if op_ty is not None:
                    return f"${self._sizeof(op_ty)}"
            except Exception:
                pass
            from pycc.ast_nodes import (
                Identifier as ASTIdentifier,
                ArrayAccess as ASTArrayAccess,
                MemberAccess as ASTMemberAccess,
                PointerMemberAccess as ASTPointerMemberAccess,
                UnaryOp as ASTUnaryOp,
            )
            if isinstance(op, ASTIdentifier):
                # Best-effort: if identifier is a known local array, return its
                # byte size (not pointer size).
                if hasattr(self, "_local_arrays") and op.name in getattr(self, "_local_arrays"):
                    ty = getattr(self, "_var_types", {}).get(f"@{op.name}")
                    if isinstance(ty, str) and ty.strip().startswith("array("):
                        inner = ty.strip()[len("array(") :]
                        if inner.endswith(")"):
                            inner = inner[:-1]
                        base_part, cnt_part = (inner.split(",", 1) + [""])[:2]
                        base_part = base_part.strip()
                        cnt_part = cnt_part.strip()
                        # 1D arrays: array(T,$N)
                        n = 1
                        if cnt_part.startswith("$"):
                            try:
                                n = int(cnt_part[1:])
                            except Exception:
                                pass

                        # Multi-dimensional arrays: parser records dims; compute
                        # total element count as product of all known dims.
                        try:
                            ad = getattr(self, "_local_array_dims", {}).get(op.name)
                        except Exception:
                            ad = None
                        if isinstance(ad, list) and ad:
                            try:
                                n2 = 1
                                for d in ad:
                                    if d is None:
                                        # unknown dimension: best-effort treat as outer dim only
                                        n2 = n
                                        break
                                    n2 *= int(d)
                                n = int(n2)
                            except Exception:
                                pass

                        return f"${self._sizeof(base_part) * max(0, n)}"
                    # fallback for local arrays
                    return "$4"

                # If parser recorded multi-dimensional dims but we didn't mark
                # it as a local array object (e.g. `char a[][4] = {...}` where
                # we infer only at IR time), still compute sizeof from dims.
                try:
                    ad = getattr(self, "_local_array_dims", {}).get(op.name)
                    if isinstance(ad, list) and len(ad) >= 2 and all(isinstance(d, int) for d in ad if d is not None):
                        # Default element type for now comes from semantic context
                        # when available; otherwise fall back to int.
                        base_part = "int"
                        try:
                            sym = f"@{op.name}"
                            bty = getattr(self, "_var_types", {}).get(sym)
                            if isinstance(bty, str) and bty.strip().startswith("array("):
                                inner = bty.strip()[len("array(") :]
                                if inner.endswith(")"):
                                    inner = inner[:-1]
                                base_part = inner.split(",", 1)[0].strip() or base_part
                        except Exception:
                            pass
                        n = 1
                        for d in ad:
                            if d is None:
                                n = 0
                                break
                            n *= int(d)
                        return f"${self._sizeof(base_part) * int(n)}"
                except Exception:
                    pass
                # Global arrays: infer total byte size using semantic context
                # (we record declared array sizes for globals when known).
                try:
                    if self._sema_ctx is not None:
                        ga = getattr(self._sema_ctx, "global_arrays", {})
                        if isinstance(ga, dict) and op.name in ga:
                            base_s, shape = ga[op.name]
                            # shape can be an int (1D element count) or a list of dims.
                            if isinstance(shape, int):
                                n = int(shape)
                            elif isinstance(shape, (list, tuple)):
                                n = 1
                                for d in shape:
                                    if d is None:
                                        # unknown size -> best-effort: treat as 0
                                        n = 0
                                        break
                                    n *= int(d)
                            else:
                                n = 0
                            return f"${self._sizeof(str(base_s)) * int(n)}"
                except Exception:
                    pass
                # Use declared local/global type when available.
                ty_s = self._operand_type_string(f"@{op.name}")
                if isinstance(ty_s, str) and ty_s:
                    return f"${self._sizeof(ty_s)}"
                # fallback
                return "$4"
            if isinstance(op, ASTUnaryOp) and op.operator == "*":
                # sizeof(*p) == sizeof(pointee)
                base = op.operand
                if isinstance(base, ASTIdentifier):
                    pty = self._operand_type_string(f"@{base.name}")
                    # If this identifier is a pointer-to-row produced by
                    # multi-dimensional array decay, prefer the row size.
                    try:
                        sym = f"@{base.name}"
                        step = getattr(self, "_ptr_step_bytes", {}).get(sym)
                        if isinstance(step, int) and step > 0:
                            return f"${step}"
                    except Exception:
                        pass
                    if isinstance(pty, str) and "*" in pty:
                        return f"${self._sizeof(pty.split('*', 1)[0].strip())}"
            if isinstance(op, ASTArrayAccess):
                # element size: int arrays are 4, char* indexing is 1. Default to 4.
                return "$4"
            if isinstance(op, (ASTMemberAccess, ASTPointerMemberAccess)):
                return "$4"
            # fallback
            return "$4"

        if isinstance(expr, Cast):
            v = self._gen_expr(expr.expression)

            # Compute the target CType via the unified resolution path.
            # This handles typedef targets (e.g. PrivPtr -> struct Priv *)
            # and pointer-to-typedef-struct (e.g. (cJSON_bool)x).
            _cast_dst_ctype = None  # type: Optional[CType]
            _cast_ast_ty = getattr(expr, "type", None)
            if _cast_ast_ty is not None and self._sema_ctx is not None:
                try:
                    _cast_dst_ctype = ast_type_to_ctype_resolved(
                        _cast_ast_ty, self._sema_ctx)
                except Exception:
                    pass

            # Float casts: int↔float/double/long double, float↔double↔long double
            _FP_TYPES = {"float", "double", "long double"}
            try:
                dst_ty = _cast_ast_ty
                # Resolve typedef in cast target type so downstream code sees
                # the real type (e.g. PrivPtr -> struct Priv *).
                _orig_is_pointer = getattr(dst_ty, "is_pointer", False)
                if dst_ty is not None and self._sema_ctx is not None:
                    _resolved_base = getattr(dst_ty, "base", "")
                    _td = getattr(self._sema_ctx, "typedefs", {}).get(_resolved_base)
                    if _td is not None:
                        # Only resolve if the original cast is NOT a pointer cast.
                        # For `(cJSON*)expr`, base="cJSON" is_pointer=True — the
                        # typedef resolves the base but the pointer level comes
                        # from the cast syntax, not the typedef.
                        if not _orig_is_pointer:
                            dst_ty = _td
                        else:
                            # Preserve pointer: resolve base but keep is_pointer.
                            from pycc.ast_nodes import Type as ASTType
                            _td_base = getattr(_td, "base", _resolved_base)
                            dst_ty = ASTType(
                                base=_td_base,
                                is_pointer=True,
                                pointer_level=getattr(dst_ty, "pointer_level", 1),
                                is_const=getattr(dst_ty, "is_const", False),
                                is_volatile=getattr(dst_ty, "is_volatile", False),
                                is_unsigned=getattr(_td, "is_unsigned", False),
                                is_signed=getattr(_td, "is_signed", False),
                            )
                dst_base = str(getattr(dst_ty, "base", "")).strip() if dst_ty else ""
                src_fp = self._var_types.get(v, "") if isinstance(v, str) else ""
                if dst_base in _FP_TYPES and src_fp not in _FP_TYPES:
                    # Build CType for the float destination.
                    _fp_ctype = _cast_dst_ctype
                    if _fp_ctype is None:
                        _fp_kind = TypeKind.FLOAT if dst_base == "float" else TypeKind.DOUBLE
                        _fp_ctype = FloatType(kind=_fp_kind)
                    if dst_base == "float":
                        conv_op = "i2f"
                    elif dst_base == "long double":
                        conv_op = "i2ld"
                    else:
                        conv_op = "i2d"
                    t = self._new_temp_typed(_fp_ctype)
                    self.instructions.append(IRInstruction(
                        op=conv_op,
                        result=t, operand1=v, meta={"fp_type": dst_base},
                        result_type=_fp_ctype))
                    return t
                if dst_base in _FP_TYPES and src_fp in _FP_TYPES and dst_base != src_fp:
                    _fp_ctype = _cast_dst_ctype
                    if _fp_ctype is None:
                        _fp_kind = TypeKind.FLOAT if dst_base == "float" else TypeKind.DOUBLE
                        _fp_ctype = FloatType(kind=_fp_kind)
                    if src_fp == "long double" or dst_base == "long double":
                        conv_op = "ld2f" if dst_base == "float" else ("ld2d" if dst_base == "double" else ("f2ld" if src_fp == "float" else "d2ld"))
                    elif dst_base == "double":
                        conv_op = "f2d"
                    else:
                        conv_op = "d2f"
                    t = self._new_temp_typed(_fp_ctype)
                    self.instructions.append(IRInstruction(
                        op=conv_op,
                        result=t, operand1=v, meta={"fp_type": dst_base},
                        result_type=_fp_ctype))
                    return t
                if dst_base not in _FP_TYPES and src_fp in _FP_TYPES:
                    _int_ctype = _cast_dst_ctype if _cast_dst_ctype is not None else IntegerType(kind=TypeKind.INT)
                    if src_fp == "long double":
                        conv_op = "ld2i"
                    elif src_fp == "float":
                        conv_op = "f2i"
                    else:
                        conv_op = "d2i"
                    t = self._new_temp_typed(_int_ctype)
                    self.instructions.append(IRInstruction(
                        op=conv_op,
                        result=t, operand1=v, meta={"fp_type": src_fp},
                        result_type=_int_ctype))
                    return t
            except Exception:
                pass
            # Integer cast: record destination type for signedness decisions
            try:
                dst_str = str(dst_ty) if dst_ty is not None else None
            except Exception:
                dst_ty = None
                dst_str = None
            if isinstance(dst_str, str):
                dst_norm = " ".join(dst_str.strip().split())
                # Only lowercase for primitive types; preserve case for
                # struct/union/enum tags (layout keys are case-sensitive).
                _base_check = dst_norm.replace("*", "").strip()
                if not (_base_check.startswith("struct ") or _base_check.startswith("union ") or _base_check.startswith("enum ")):
                    dst_norm = dst_norm.lower()
                # Parser encodes explicit signedness via Type flags while keeping
                # base == "char".
                if dst_norm == "char" and dst_ty is not None:
                    try:
                        if getattr(dst_ty, "is_signed", False):
                            dst_norm = "signed char"
                            dst_str = "signed char"
                        elif getattr(dst_ty, "is_unsigned", False):
                            dst_norm = "unsigned char"
                            dst_str = "unsigned char"
                    except Exception:
                        pass
                # Unify common spellings.
                if dst_norm == "unsigned short int":
                    dst_norm = "unsigned short"
                if dst_norm in {"signed short int", "signed signed short"}:
                    dst_norm = "signed short"
                if dst_norm == "short int":
                    dst_norm = "short"
                # Some parser paths may redundantly encode unsigned in both the
                # base string and the flag, yielding strings like:
                #   "unsigned unsigned short"
                if dst_norm.startswith("unsigned unsigned "):
                    dst_norm = dst_norm.replace("unsigned unsigned ", "unsigned ", 1)

                # Keep dst_str in sync with the normalized spelling for later
                # _var_types recording.
                dst_str = dst_norm

                # Determine the CType for the cast destination (used for
                # _new_temp_typed).  Fall back to building from dst_norm when
                # the resolved CType is unavailable.
                _int_cast_ctype = _cast_dst_ctype  # type: Optional[CType]

                if dst_norm in {"unsigned char", "char"} and not getattr(dst_ty, "is_pointer", False):
                    # Truncate to 8 bits (zero-extend on read by masking).
                    _tc = _int_cast_ctype if _int_cast_ctype is not None else IntegerType(kind=TypeKind.CHAR, is_unsigned=(dst_norm == "unsigned char"))
                    t = self._new_temp_typed(_tc)
                    self.instructions.append(IRInstruction(op="binop", result=t, operand1=v, operand2="$255", label="&", result_type=_tc))
                    v = t
                elif dst_norm == "signed char":
                    # Truncate to 8 bits then sign-extend back to the IR's
                    # working width.
                    #
                    # This is required for cases like:
                    #   x == (signed char)-116
                    # where the RHS constant must compare as -116, not 140.
                    _tc = IntegerType(kind=TypeKind.CHAR, is_unsigned=False)
                    t = self._new_temp_typed(_tc)
                    self.instructions.append(IRInstruction(op="binop", result=t, operand1=v, operand2="$255", label="&", result_type=_tc))
                    _tc2 = _int_cast_ctype if _int_cast_ctype is not None else _tc
                    t2 = self._new_temp_typed(_tc2)
                    self.instructions.append(IRInstruction(op="sext8", result=t2, operand1=t, result_type=_tc2))
                    v = t2
                elif dst_norm in {"unsigned short", "unsigned short int", "short", "short int"} and not getattr(dst_ty, "is_pointer", False):
                    # Truncate to 16 bits.
                    # For signed `short`, also sign-extend so comparisons use
                    # the same representation as loads (which are sign-extended).
                    dst_canon = self._canon_int_type(dst_str)
                    _tc = _int_cast_ctype if _int_cast_ctype is not None else IntegerType(kind=TypeKind.SHORT, is_unsigned=(dst_canon != "short"))
                    t = self._new_temp_typed(_tc)
                    self.instructions.append(IRInstruction(op="binop", result=t, operand1=v, operand2="$65535", label="&", result_type=_tc))
                    if dst_canon == "short":
                        t2 = self._new_temp_typed(_tc)
                        self.instructions.append(IRInstruction(op="sext16", result=t2, operand1=t, result_type=_tc))
                        v = t2
                    else:
                        v = t
                elif dst_norm in {"signed short", "signed short int"} and not getattr(dst_ty, "is_pointer", False):
                    # Truncate to 16 bits then sign-extend.
                    _tc = _int_cast_ctype if _int_cast_ctype is not None else IntegerType(kind=TypeKind.SHORT, is_unsigned=False)
                    t = self._new_temp_typed(_tc)
                    self.instructions.append(IRInstruction(op="binop", result=t, operand1=v, operand2="$65535", label="&", result_type=_tc))
                    t2 = self._new_temp_typed(_tc)
                    self.instructions.append(IRInstruction(op="sext16", result=t2, operand1=t, result_type=_tc))
                    v = t2
                # Preserve pointer-ness in casted values.
                # IMPORTANT: do not clobber _var_types of named variables when
                # the cast would lose struct/union type information needed for
                # member offset resolution. For example, `(void*)root` should
                # NOT change root's type from "cJSON*" to "void*".
                #
                # NOTE: We intentionally do NOT update _sym_table for named
                # variables here.  The cast result should use a new temp if
                # the caller needs a differently-typed value.  Modifying the
                # source operand's CType in the symbol table would violate
                # Requirement 5.1.  The _var_types update is kept for compat.
                cast_ty = None
                if getattr(dst_ty, "is_pointer", False):
                    cast_ty = dst_str if "*" in dst_str else f"{dst_str}*"
                else:
                    cast_ty = dst_str
                if isinstance(v, str) and v.startswith("@"):
                    # Named variable: only update _var_types if the new type
                    # doesn't lose struct/union pointer info that member
                    # access needs.  Never touch _sym_table for named vars.
                    old_ty = self._var_types.get(v, "")
                    if isinstance(old_ty, str) and "*" in old_ty:
                        old_base = old_ty.replace("*", "").strip()
                        new_base = cast_ty.replace("*", "").strip() if isinstance(cast_ty, str) else ""
                        # Don't clobber if old type has a struct/union base
                        # and new type is void or a different struct.
                        if old_base and self._is_struct_or_union_type(old_base):
                            if new_base in ("void", "") or new_base != old_base:
                                pass  # keep old type
                            else:
                                self._var_types[v] = cast_ty
                        else:
                            self._var_types[v] = cast_ty
                    else:
                        self._var_types[v] = cast_ty
                else:
                    self._var_types[v] = cast_ty
                    if self._sym_table and _cast_dst_ctype is not None:
                        self._sym_table.insert(v, _cast_dst_ctype)
            # If casting to pointer, allow integer literal 0 to stay 0; otherwise passthrough.
            return v
        if isinstance(expr, Identifier):
            # enum constants lower to immediates
            if hasattr(self, "_enum_constants") and expr.name in self._enum_constants:
                return f"${self._enum_constants[expr.name]}"
            # Resolve function-local statics.
            if hasattr(self, "_local_static_syms"):
                m = getattr(self, "_local_static_syms", {})
                if expr.name in m:
                    return f"@{m[expr.name]}"

            sym = self._resolve_name(expr.name)
            # Array-to-pointer decay in rvalue context: emit explicit addr-of.
            # Our semantic/type system is minimal; detect arrays by the presence of
            # a declared array_size on the declaration node (recorded earlier by decl).
            # Since IR is stringly-typed, we conservatively treat any symbol that was
            # declared as an array in this function as decaying to its address.
            # NOTE: `self._local_arrays` stores plain names (without '@').
            if hasattr(self, "_local_arrays") and expr.name in getattr(self, "_local_arrays"):
                t = self._new_temp()
                ins = IRInstruction(op="mov_addr", result=t, operand1=sym)
                # Preserve array element type info on the decayed pointer temp
                # so `load_index/store_index` can compute correct element size.
                try:
                    ty = self._var_types.get(sym)
                    if isinstance(ty, str) and ty.strip().startswith("array("):
                        inner = ty.strip()[len("array(") :]
                        if inner.endswith(")"):
                            inner = inner[:-1]
                        base_part = inner.split(",", 1)[0].strip()
                        self._var_types[t] = f"{base_part}*"
                except Exception:
                    pass

                # Register decayed pointer in symbol table: array -> pointer to element.
                if self._sym_table:
                    arr_ct = self._sym_table.lookup(sym)
                    if isinstance(arr_ct, CArrayType) and arr_ct.element is not None:
                        decay_ct = PointerType(kind=TypeKind.POINTER, pointee=arr_ct.element)
                        self._sym_table.insert(t, decay_ct)
                    elif isinstance(arr_ct, PointerType):
                        self._sym_table.insert(t, arr_ct)

                # If this is a multi-dimensional local array with known inner
                # dimension, record pointer step bytes for (p + 1) scaling.
                # We rely on a generator-level map populated during decl lowering.
                try:
                    ad = getattr(self, "_local_array_dims", {}).get(expr.name)
                except Exception:
                    ad = None
                if isinstance(ad, list) and len(ad) >= 2 and isinstance(ad[1], int):
                    base_part = None
                    try:
                        ty = self._var_types.get(sym)
                        if isinstance(ty, str) and ty.strip().startswith("array("):
                            inner = ty.strip()[len("array(") :]
                            if inner.endswith(")"):
                                inner = inner[:-1]
                            base_part = inner.split(",", 1)[0].strip()
                    except Exception:
                        base_part = None
                    if isinstance(base_part, str) and base_part:
                        elem_sz = _type_size_bytes(self._sema_ctx, base_part)
                        if isinstance(elem_sz, int) and elem_sz > 0:
                            step = int(ad[1]) * int(elem_sz)
                            ins.meta["ptr_step_bytes"] = step
                            # Also record it in a generator-level map so it can
                            # be propagated through moves into local symbols.
                            self._ptr_step_bytes[t] = step

                self.instructions.append(ins)
                return t
            # If this identifier is known to be a pointer variable, preserve
            # its type on the symbol reference so later ops (ptr arith, loads)
            # can make sizing decisions.
            try:
                ty = getattr(self, "_var_types", {}).get(sym)
                if isinstance(ty, str):
                    self._var_types[sym] = ty
                elif self._sema_ctx is not None:
                    gty = getattr(self._sema_ctx, "global_types", {}).get(expr.name)
                    if isinstance(gty, str) and gty.strip() in ("float", "double", "long double"):
                        self._var_types[sym] = gty.strip()
            except Exception:
                pass
            return sym
        if isinstance(expr, FunctionDecl):
            # Function designator in expression context decays to a function
            # pointer; represent it as a direct symbol reference.
            return f"@{expr.name}"
        if isinstance(expr, MemberAccess):
            base = self._gen_expr(expr.object)
            # If the member is an aggregate, return an lvalue address (pointer)
            # so chained member access works: `s.b.x`.
            try:
                if self._sema_ctx is not None and isinstance(base, str):
                    bty = self._var_types.get(base)
                    if (bty is None or bty == "") and base.startswith("@"): 
                        bty = getattr(self._sema_ctx, "global_types", {}).get(base[1:], None)
                    if isinstance(bty, str) and bty.strip().endswith("*"):
                        bty = bty.strip()[:-1].strip()
                    if isinstance(bty, str):
                        # Resolve typedef to find the layout key.
                        resolved_bty = bty
                        seen_td = set()
                        while resolved_bty and resolved_bty not in seen_td:
                            if resolved_bty.startswith("struct ") or resolved_bty.startswith("union "):
                                break
                            seen_td.add(resolved_bty)
                            td = getattr(self._sema_ctx, "typedefs", {}).get(resolved_bty)
                            if td is None:
                                break
                            tb = getattr(td, "base", None)
                            if isinstance(tb, str):
                                resolved_bty = tb.strip()
                            else:
                                break
                        layout = getattr(self._sema_ctx, "layouts", {}).get(resolved_bty)
                        if layout is None:
                            layout = getattr(self._sema_ctx, "layouts", {}).get(bty)
                        if layout is not None:
                            mtypes = getattr(layout, "member_types", {}) or {}
                            mty = mtypes.get(expr.member)
                            if isinstance(mty, str) and self._is_struct_or_union_type(mty):
                                # Resolve member CType for type annotation.
                                member_ctype = self._lookup_member_ctype(base, expr.member)
                                if member_ctype is not None:
                                    ptr_ctype = PointerType(kind=TypeKind.POINTER, pointee=member_ctype)
                                    taddr = self._new_temp_typed(ptr_ctype)
                                else:
                                    taddr = self._new_temp()
                                    self._var_types[taddr] = f"{mty}*"
                                aom_meta = {"member_type": mty}
                                if member_ctype is not None:
                                    aom_meta["member_ctype"] = member_ctype
                                rt = PointerType(kind=TypeKind.POINTER, pointee=member_ctype) if member_ctype else None
                                # If base is a pointer (e.g. from addr_of_member_ptr),
                                # use addr_of_member_ptr instead of addr_of_member.
                                _base_is_ptr = False
                                _bty_c = self._var_types.get(base, "")
                                if isinstance(_bty_c, str) and ("*" in _bty_c or _bty_c.strip() == "ptr"):
                                    _base_is_ptr = True
                                elif self._sym_table:
                                    _base_ct = self._sym_table.lookup(base)
                                    if _base_ct is not None and isinstance(_base_ct, PointerType):
                                        _base_is_ptr = True
                                _aom_op = "addr_of_member_ptr" if _base_is_ptr else "addr_of_member"
                                self.instructions.append(IRInstruction(op=_aom_op, result=taddr, operand1=base, operand2=expr.member, meta=aom_meta, result_type=rt))
                                return taddr
            except Exception:
                pass

            t = self._new_temp()
            # Look up member type and attach to IR meta for codegen.
            load_meta = {}
            member_ct = self._lookup_member_ctype(base, expr.member)
            try:
                if self._sema_ctx is not None and isinstance(base, str):
                    bty = self._var_types.get(base, "")
                    if isinstance(bty, str) and bty.strip().endswith("*"):
                        bty = bty.strip()[:-1].strip()
                    resolved_bty = self._resolve_elem_type(bty) if bty else bty
                    layout = getattr(self._sema_ctx, "layouts", {}).get(resolved_bty)
                    if layout is None:
                        layout = getattr(self._sema_ctx, "layouts", {}).get(bty)
                    if layout is not None:
                        mtypes = getattr(layout, "member_types", {}) or {}
                        mty = mtypes.get(expr.member)
                        if isinstance(mty, str):
                            load_meta["member_type"] = mty
                            if "*" in mty or mty.strip() in ("float", "double", "long double"):
                                self._var_types[t] = mty
            except Exception:
                pass
            if member_ct is not None:
                load_meta["member_ctype"] = member_ct
                # Register result temp with member CType in symbol table.
                if self._sym_table:
                    self._sym_table.insert(t, member_ct)
            # If the base is a pointer (e.g. from addr_of_member_ptr for a
            # struct sub-member like p->hooks), use load_member_ptr instead
            # of load_member so codegen loads the pointer value first.
            base_is_ptr = False
            bty_check = self._var_types.get(base, "")
            if isinstance(bty_check, str) and ("*" in bty_check or bty_check.strip() == "ptr"):
                base_is_ptr = True
            elif self._sym_table:
                base_ct = self._sym_table.lookup(base)
                if base_ct is not None and isinstance(base_ct, PointerType):
                    base_is_ptr = True
            op_name = "load_member_ptr" if base_is_ptr else "load_member"
            self.instructions.append(IRInstruction(op=op_name, result=t, operand1=base, operand2=expr.member, meta=load_meta if load_meta else None, result_type=member_ct))
            return t
        # Address-of a member: &obj.member
        if isinstance(expr, UnaryOp) and expr.operator == "&" and isinstance(expr.operand, MemberAccess):
            ma = expr.operand
            base = self._gen_expr(ma.object)
            # Look up member CType for type annotation.
            member_ct = self._lookup_member_ctype(base, ma.member)
            if member_ct is not None:
                ptr_ctype = PointerType(kind=TypeKind.POINTER, pointee=member_ct)
                t = self._new_temp_typed(ptr_ctype)
            else:
                t = self._new_temp()
            aom_rt = PointerType(kind=TypeKind.POINTER, pointee=member_ct) if member_ct else None
            self.instructions.append(IRInstruction(op="addr_of_member", result=t, operand1=base, operand2=ma.member, result_type=aom_rt))
            # Preserve base type on the lvalue symbol so codegen can resolve
            # offsets/sizes even for globals.
            try:
                if isinstance(base, str) and base.startswith("@") and self._sema_ctx is not None:
                    bty = getattr(self._sema_ctx, "global_types", {}).get(base[1:])
                    if isinstance(bty, str):
                        self._var_types[base] = bty
            except Exception:
                pass
            # best-effort: preserve pointer type for codegen width decisions
            try:
                if self._sema_ctx is not None and isinstance(getattr(ma.object, "type", None), Type):
                    # fallback: we don't have full typing; leave var_types unset
                    pass
            except Exception:
                pass
            return t
        # Address-of a pointer member: &p->member
        if isinstance(expr, UnaryOp) and expr.operator == "&" and isinstance(expr.operand, PointerMemberAccess):
            pma = expr.operand
            base = self._gen_expr(pma.pointer)
            member_ct = self._lookup_member_ctype(base, pma.member)
            if member_ct is not None:
                ptr_ctype = PointerType(kind=TypeKind.POINTER, pointee=member_ct)
                t = self._new_temp_typed(ptr_ctype)
            else:
                t = self._new_temp()
            aom_rt = PointerType(kind=TypeKind.POINTER, pointee=member_ct) if member_ct else None
            self.instructions.append(IRInstruction(op="addr_of_member_ptr", result=t, operand1=base, operand2=pma.member, result_type=aom_rt))
            return t
        # Address-of an array element: &arr[i]
        # When the element is a struct/union, _gen_expr(ArrayAccess) already
        # returns an addr_index result (a pointer to the element). In that case
        # &arr[i] should return the same pointer, not take its stack address.
        if isinstance(expr, UnaryOp) and expr.operator == "&" and isinstance(expr.operand, ArrayAccess):
            v = self._gen_expr(expr.operand)
            # Check if the result is already a pointer (from addr_index for struct elements)
            if self._sym_table:
                ct = self._sym_table.lookup(v)
                if ct is not None and isinstance(ct, PointerType):
                    return v
            # Also check _var_types
            vty = self._var_types.get(v, "")
            if isinstance(vty, str) and "*" in vty:
                return v
            # Scalar element: take address normally
            t = self._new_temp()
            self.instructions.append(IRInstruction(op="addr_of", result=t, operand1=v))
            return t
        if isinstance(expr, ArrayAccess):
            # Multi-dimensional array indexing:
            # - For `a[i]` where `a` is a 2D local array, lower to an lvalue row
            #   address (a pointer) so outer indexing can proceed.
            # - For `a[i][j]`, the AST is nested ArrayAccess. The outer index
            #   consumes the row pointer computed by the inner access.

            # Outer access of nested indexing: `(...)[j]`.
            if isinstance(expr.array, ArrayAccess):
                base_row = self._gen_expr(expr.array)
                idx2 = self._gen_expr(expr.index)
                # Lower as: addr_index(base_row, idx2) then load(addr)
                # This avoids `load_index` width inference pitfalls.
                addr = self._new_temp()
                self.instructions.append(IRInstruction(op="addr_index", result=addr, operand1=base_row, operand2=idx2))
                t2 = self._new_temp()
                ins_load = IRInstruction(op="load", result=t2, operand1=addr)

                # Type hints for correct load width: addr must be a pointer to
                # element type (e.g. char*).
                try:
                    bty = getattr(self, "_var_types", {}).get(base_row)
                    if isinstance(bty, str) and bty.strip().startswith("array("):
                        inner = bty.strip()[len("array(") :]
                        if inner.endswith(")"):
                            inner = inner[:-1]
                        base_part = inner.split(",", 1)[0].strip()
                        if base_part:
                            self._var_types[addr] = f"{base_part}*"
                            self._var_types[t2] = base_part
                            # Force load width from element type. This makes
                            # nested `a[i][j]` robust even if codegen's var_type
                            # propagation is imperfect.
                            try:
                                ins_load.meta["load_size_bytes"] = int(_type_size_bytes(self._sema_ctx, base_part))
                            except Exception:
                                pass
                            # Also ensure index scaling uses element size (not the
                            # row stride carried by the row-pointer temp).
                            try:
                                ins_load_addr = self.instructions[-1]
                                if isinstance(ins_load_addr, IRInstruction) and ins_load_addr.op == "addr_index" and ins_load_addr.result == addr:
                                    esz = int(_type_size_bytes(self._sema_ctx, base_part))
                                    if esz > 0:
                                        ins_load_addr.meta["ptr_step_bytes"] = esz
                            except Exception:
                                pass
                            # load width is selected from the pointer pointee type;
                            # make sure it is attached to the address temp.
                except Exception:
                    pass
                # Register nested indexing temps in symbol table.
                if self._sym_table:
                    base_row_ct = self._sym_table.lookup(base_row)
                    nested_elem_ct = None
                    if isinstance(base_row_ct, CArrayType) and base_row_ct.element is not None:
                        nested_elem_ct = base_row_ct.element
                    elif isinstance(base_row_ct, PointerType) and base_row_ct.pointee is not None:
                        nested_elem_ct = base_row_ct.pointee
                    if nested_elem_ct is not None:
                        self._sym_table.insert(addr, PointerType(kind=TypeKind.POINTER, pointee=nested_elem_ct))
                        self._sym_table.insert(t2, nested_elem_ct)
                self.instructions.append(ins_load)
                return t2

            base = self._gen_expr(expr.array)
            idx = self._gen_expr(expr.index)

            # If base is a row-pointer temp (from nested indexing), carry its
            # ptr_step_bytes onto the load_index instruction so codegen can
            # scale the index correctly.
            base_step = None
            try:
                if isinstance(base, str):
                    base_step = getattr(self, "_ptr_step_bytes", {}).get(base)
            except Exception:
                base_step = None

            # If indexing yields another array (e.g. `a[i]` where `a` is a 2D
            # local array), produce an lvalue address of the row.
            try:
                if isinstance(expr.array, Identifier):
                    dims = getattr(self, "_local_array_dims", {}).get(expr.array.name)
                    sym = f"@{expr.array.name}"
                    bty = getattr(self, "_var_types", {}).get(sym)
                    if isinstance(dims, list) and len(dims) >= 2:
                        row_ptr = self._new_temp()
                        ins_row = IRInstruction(op="addr_index", result=row_ptr, operand1=base, operand2=idx)
                        # Step for indexing *rows* is sizeof(row) = dim1 * sizeof(elem)
                        try:
                            base_part = None
                            if isinstance(bty, str) and bty.strip().startswith("array("):
                                inner = bty.strip()[len("array(") :]
                                if inner.endswith(")"):
                                    inner = inner[:-1]
                                base_part = inner.split(",", 1)[0].strip()
                            if isinstance(base_part, str) and base_part and isinstance(dims[1], int):
                                elem_sz = _type_size_bytes(self._sema_ctx, base_part)
                                if isinstance(elem_sz, int) and elem_sz > 0:
                                    step = int(dims[1]) * int(elem_sz)
                                    # Attach the row stride (bytes) for pointer arithmetic
                                    # on the row pointer itself.
                                    ins_row.meta["ptr_step_bytes"] = step
                                    self._ptr_step_bytes[row_ptr] = step
                                    # Row pointer points to the row object: element type is
                                    # the full row (e.g. array(char, $4)), so that later
                                    # `load_index` on it will not treat it as a scalar pointer.
                                    self._var_types[row_ptr] = f"array({base_part}, ${int(dims[1])})"
                        except Exception:
                            pass
                        self.instructions.append(ins_row)
                        return row_ptr
            except Exception:
                pass

            # If indexing yields an aggregate (struct/union), we must produce an
            # lvalue address, not load a scalar value.
            try:
                if self._sema_ctx is not None and isinstance(base, str):
                    # Infer element type from the base symbol's recorded type.
                    bty = self._var_types.get(base)
                    if (bty is None or bty == "") and base.startswith("@"):
                        bty = getattr(self._sema_ctx, "global_types", {}).get(base[1:], None)
                    elem_ty = None
                    if isinstance(bty, str) and bty.strip().startswith("array("):
                        inner = bty.strip()[len("array(") :]
                        if inner.endswith(")"):
                            inner = inner[:-1]
                        elem_ty = inner.split(",", 1)[0].strip()
                    elif isinstance(bty, str) and bty.strip().endswith("*"):
                        elem_ty = bty.strip()[:-1].strip()

                    # Special-case: unsized arrays like `struct S a[] = {...}`
                    # are recorded in global_types as just "struct S".
                    if elem_ty is None and isinstance(bty, str) and self._is_struct_or_union_type(bty.strip()):
                        elem_ty = bty.strip()

                    if isinstance(elem_ty, str) and self._is_struct_or_union_type(elem_ty):
                        taddr = self._new_temp()
                        self.instructions.append(IRInstruction(op="addr_index", result=taddr, operand1=base, operand2=idx))
                        # Preserve pointer type for later member access.
                        self._var_types[taddr] = f"{elem_ty}*"
                        # Register in symbol table: pointer to the struct element.
                        if self._sym_table:
                            base_ct = self._sym_table.lookup(base)
                            elem_ct = None
                            if isinstance(base_ct, CArrayType) and base_ct.element is not None:
                                elem_ct = base_ct.element
                            elif isinstance(base_ct, PointerType) and base_ct.pointee is not None:
                                elem_ct = base_ct.pointee
                            if elem_ct is not None:
                                self._sym_table.insert(taddr, PointerType(kind=TypeKind.POINTER, pointee=elem_ct))
                        return taddr
            except Exception:
                pass

            t = self._new_temp()
            ins = IRInstruction(op="load_index", result=t, operand1=base, operand2=idx)
            if isinstance(base_step, int) and base_step > 0:
                ins.meta["ptr_step_bytes"] = int(base_step)
            self.instructions.append(ins)
            # If indexing a row pointer temp (from a[i] in a[i][j]), preserve
            # the element type so codegen can load the correct width.
            try:
                bty = getattr(self, "_var_types", {}).get(base)
                if isinstance(bty, str) and bty.strip().endswith("*"):
                    self._var_types[t] = bty.strip()[:-1].strip()
            except Exception:
                pass
            # Register result in symbol table with element CType.
            if self._sym_table:
                base_ct = self._sym_table.lookup(base)
                elem_ct = None
                if isinstance(base_ct, PointerType) and base_ct.pointee is not None:
                    elem_ct = base_ct.pointee
                elif isinstance(base_ct, CArrayType) and base_ct.element is not None:
                    elem_ct = base_ct.element
                if elem_ct is not None:
                    self._sym_table.insert(t, elem_ct)
            return t
        if isinstance(expr, PointerMemberAccess):
            base = self._gen_expr(expr.pointer)
            # Propagate struct type info so codegen can resolve member offsets.
            meta = {}
            base_ty = self._var_types.get(base, "")
            if isinstance(base_ty, str) and base_ty.strip().endswith("*"):
                struct_ty = base_ty.strip()[:-1].strip()
                if struct_ty:
                    meta["struct_type"] = struct_ty
            # Look up member type from layout.
            try:
                if self._sema_ctx is not None:
                    sty = struct_ty if 'struct_ty' in dir() and struct_ty else ""
                    resolved_sty = self._resolve_elem_type(sty) if sty else sty
                    layout = getattr(self._sema_ctx, "layouts", {}).get(resolved_sty)
                    if layout is None and sty:
                        layout = getattr(self._sema_ctx, "layouts", {}).get(sty)
                    if layout is not None:
                        mtypes = getattr(layout, "member_types", {}) or {}
                        mty = mtypes.get(expr.member)
                        if isinstance(mty, str):
                            meta["member_type"] = mty
                            # If the member is a struct/union, return an lvalue
                            # address (pointer) so chained access works: p->hooks.reallocate
                            if self._is_struct_or_union_type(mty):
                                member_ctype = self._lookup_member_ctype(base, expr.member)
                                if member_ctype is not None:
                                    ptr_ctype = PointerType(kind=TypeKind.POINTER, pointee=member_ctype)
                                    taddr = self._new_temp_typed(ptr_ctype)
                                else:
                                    taddr = self._new_temp()
                                    self._var_types[taddr] = f"{mty}*"
                                aom_meta = dict(meta)
                                if member_ctype is not None:
                                    aom_meta["member_ctype"] = member_ctype
                                rt = PointerType(kind=TypeKind.POINTER, pointee=member_ctype) if member_ctype else None
                                self.instructions.append(IRInstruction(op="addr_of_member_ptr", result=taddr, operand1=base, operand2=expr.member, meta=aom_meta, result_type=rt))
                                return taddr
                            if "*" in mty or mty.strip() in ("float", "double", "long double"):
                                self._var_types[base + "_member_" + expr.member] = mty
            except Exception:
                pass
            # Scalar/pointer member: load the value.
            t = self._new_temp()
            member_ct = self._lookup_member_ctype(base, expr.member)
            if member_ct is not None:
                meta["member_ctype"] = member_ct
                if self._sym_table:
                    self._sym_table.insert(t, member_ct)
            # Propagate float/double type to _var_types for codegen.
            try:
                mty_str = meta.get("member_type", "")
                if isinstance(mty_str, str) and mty_str.strip() in ("float", "double", "long double"):
                    self._var_types[t] = mty_str.strip()
                elif isinstance(mty_str, str) and "*" in mty_str:
                    self._var_types[t] = mty_str
            except Exception:
                pass
            self.instructions.append(IRInstruction(op="load_member_ptr", result=t, operand1=base, operand2=expr.member, meta=meta if meta else None, result_type=member_ct))
            return t
        if isinstance(expr, Assignment):
            rhs = self._gen_expr(expr.value)
            # only handle identifier targets 
            if isinstance(expr.target, Identifier):
                # local statics lower to unique global symbols
                if hasattr(self, "_local_static_syms") and expr.target.name in getattr(self, "_local_static_syms", {}):
                    dst = f"@{self._local_static_syms[expr.target.name]}"
                else:
                    dst = self._resolve_name(expr.target.name)
                if expr.operator == "=":
                    # Preserve pointer type on the destination when assigning
                    # from a pointer-typed value.
                    try:
                        rty = getattr(self, "_var_types", {}).get(rhs)
                        # If RHS is a decayed local array address, it might not
                        # have a pointer type recorded; derive it from the array.
                        if not (isinstance(rty, str) and "*" in rty) and hasattr(self, "_local_arrays"):
                            for name in self._local_arrays:
                                aty = self._var_types.get(f"@{name}")
                                if not (isinstance(aty, str) and aty.strip().startswith("array(")):
                                    continue
                                inner = aty.strip()[len("array(") :]
                                if inner.endswith(")"):
                                    inner = inner[:-1]
                                base_part = inner.split(",", 1)[0].strip()
                                # Best-effort: if dst is pointer (or unknown),
                                # and RHS is from some local array decay, use
                                # that array's element type.
                                if dst not in self._var_types or self._var_types.get(dst) in {None, "", "char*"}:
                                    rty = f"{base_part}*"
                                    break

                        if isinstance(rty, str) and "*" in rty:
                            self._var_types[dst] = rty
                        # If we have semantic type info for the LHS identifier,
                        # prefer it. This is required for cases like:
                        #   struct S *p = arr;
                        # where the RHS is an address temp typed as `char*`
                        # (array-to-pointer decay currently only carries basic
                        # element types).
                        if self._sema_ctx is not None:
                            sym = dst[1:] if dst.startswith("@") else dst
                            ty = getattr(self._sema_ctx, "var_types", {}).get(sym)
                            if ty is None:
                                ty = getattr(self._sema_ctx, "global_types", {}).get(sym)
                            if ty is not None:
                                self._var_types[dst] = str(ty)
                    except Exception:
                        pass
                    # Struct/union by-value assignment: emit struct_copy with size.
                    dst_ty = self._var_types.get(dst, "")
                    if isinstance(dst_ty, str) and (dst_ty.strip().startswith("struct ") or dst_ty.strip().startswith("union ")):
                        layout = getattr(self._sema_ctx, "layouts", {}).get(dst_ty.strip()) if self._sema_ctx else None
                        sz = int(getattr(layout, "size", 0) or 0) if layout else 0
                        if sz > 0:
                            self.instructions.append(IRInstruction(op="struct_copy", result=dst, operand1=rhs, meta={"size": sz}))
                            return dst
                    mov_meta: dict = {}
                    if self._is_volatile_sym(dst):
                        mov_meta["volatile"] = True
                    self.instructions.append(IRInstruction(op="mov", result=dst, operand1=rhs, meta=mov_meta if mov_meta else None))
                    return dst
                # compound assigns: a += b => a = a + b
                cur = self._gen_expr(expr.target)
                bop = expr.operator[:-1]

                # Best-effort pointer compound arithmetic scaling.
                # If `cur` is a pointer and rhs is integer, scale rhs by pointee size.
                cty = getattr(self, "_var_types", {}).get(cur)
                rty = getattr(self, "_var_types", {}).get(rhs)
                cur_is_ptr = (isinstance(cty, str) and "*" in cty) or self._lookup_pointer_ctype(cur) is not None
                rhs_is_ptr = isinstance(rty, str) and "*" in rty
                if bop in {"+", "-"} and cur_is_ptr and not rhs_is_ptr:
                    # String primary, CType fallback (casts update _var_types
                    # but not _sym_table for named vars).
                    sz = self._sizeof(cty.split("*", 1)[0].strip()) if isinstance(cty, str) and "*" in cty else 0
                    if sz <= 0:
                        ct_sz = self._pointee_size_from_ctype(cur)
                        if ct_sz is not None and ct_sz > 0:
                            sz = ct_sz
                    if sz != 1:
                        s = self._new_temp()
                        self.instructions.append(IRInstruction(op="binop", result=s, operand1=rhs, operand2=f"${sz}", label="*"))
                        rhs = s

                t = self._new_temp()
                self.instructions.append(IRInstruction(op="binop", result=t, operand1=cur, operand2=rhs, label=bop))
                # Preserve pointer type for the updated variable.
                if isinstance(cty, str) and "*" in cty:
                    self._var_types[t] = cty
                    self._var_types[dst] = cty
                    # Also register in symbol table.
                    cur_ct = self._lookup_pointer_ctype(cur)
                    if cur_ct is not None and self._sym_table:
                        self._sym_table.insert(t, cur_ct)
                        self._sym_table.insert(dst, cur_ct)
                # For narrow integer lvalues (char/short), compound assignment
                # must convert the computed int result back to the lvalue type.
                # Best-effort: truncate to 16 bits for short.
                elif isinstance(cty, str) and self._canon_int_type(cty) in {"short", "unsigned short"}:
                    t2 = self._new_temp()
                    self.instructions.append(IRInstruction(op="binop", result=t2, operand1=t, operand2="$65535", label="&"))
                    cty_n = self._canon_int_type(cty)
                    # Preserve signedness on the temp for later loads.
                    self._var_types[t2] = cty_n

                    # If the lvalue is signed short, the stored value should
                    # behave like a promoted short in later expressions.
                    # Masking yields 0..65535, so materialize sign via sext16.
                    if cty_n == "short":
                        t3 = self._new_temp()
                        self.instructions.append(IRInstruction(op="sext16", result=t3, operand1=t2))
                        self._var_types[t3] = "short"
                        t = t3
                    else:
                        t = t2
                    # Ensure the destination keeps its narrow type.
                    self._var_types[dst] = cty_n
                comp_mov_meta: dict = {}
                if self._is_volatile_sym(dst):
                    comp_mov_meta["volatile"] = True
                self.instructions.append(IRInstruction(op="mov", result=dst, operand1=t, meta=comp_mov_meta if comp_mov_meta else None))
                return dst



            # handle pointer deref compound assign: *p op= rhs
            if (
                isinstance(expr.target, UnaryOp)
                and expr.target.operator == "*"
                and expr.operator != "="
            ):
                addr = self._gen_expr(expr.target.operand)
                # propagate pointer type from operand to the computed address
                try:
                    op_ty = getattr(self, "_var_types", {}).get(addr)
                    if not op_ty and isinstance(expr.target.operand, Identifier):
                        op_ty = getattr(self, "_var_types", {}).get(f"@{expr.target.operand.name}")
                    if isinstance(op_ty, str) and "*" in op_ty:
                        self._var_types[addr] = op_ty
                except Exception:
                    op_ty = None

                # Load current value at *addr, do operation, then store back.
                cur = self._new_temp()
                # Check if the pointer dereference accesses volatile memory.
                _deref_vol = self._is_volatile_deref(expr.target.operand)
                self.instructions.append(IRInstruction(op="load", result=cur, operand1=addr,
                                                       meta={"volatile": True} if _deref_vol else None))

                # Best-effort: propagate pointee scalar type onto the loaded temp.
                # This is needed so later ops like `>>` can choose signed vs unsigned.
                addr_ty = getattr(self, "_var_types", {}).get(addr, "")
                addr_ty_n = addr_ty.strip().lower() if isinstance(addr_ty, str) else ""
                if isinstance(addr_ty_n, str) and "*" in addr_ty_n:
                    pointee = addr_ty_n.split("*", 1)[0].strip()
                    pointee = self._canon_int_type(pointee)
                    if pointee in {"char", "unsigned char", "short", "unsigned short", "int", "unsigned int"}:
                        self._var_types[cur] = pointee

                bop = expr.operator[:-1]
                cty = getattr(self, "_var_types", {}).get(cur)
                rty = getattr(self, "_var_types", {}).get(rhs)

                # Best-effort pointer compound arithmetic scaling.
                cur_is_ptr2 = (isinstance(cty, str) and "*" in cty) or self._lookup_pointer_ctype(cur) is not None
                rhs_is_ptr2 = isinstance(rty, str) and "*" in rty
                if bop in {"+", "-"} and cur_is_ptr2 and not rhs_is_ptr2:
                    # String primary, CType fallback.
                    sz = self._sizeof(cty.split("*", 1)[0].strip()) if isinstance(cty, str) and "*" in cty else 0
                    if sz <= 0:
                        ct_sz = self._pointee_size_from_ctype(cur)
                        if ct_sz is not None and ct_sz > 0:
                            sz = ct_sz
                    if sz != 1:
                        s = self._new_temp()
                        self.instructions.append(
                            IRInstruction(op="binop", result=s, operand1=rhs, operand2=f"${sz}", label="*")
                        )
                        rhs = s

                t = self._new_temp()
                self.instructions.append(IRInstruction(op="binop", result=t, operand1=cur, operand2=rhs, label=bop))
                # For narrow integer pointees, store width is handled by codegen,
                # but we still need to materialize truncation and (for signed
                # short/char) sign extension so later loads/compares match C.
                addr_ty = getattr(self, "_var_types", {}).get(addr, "")
                addr_ty_n = addr_ty.strip().lower() if isinstance(addr_ty, str) else ""
                if isinstance(addr_ty_n, str) and "*" in addr_ty_n:
                    pointee = addr_ty_n.split("*", 1)[0].strip()
                    pointee = self._canon_int_type(pointee)
                    if pointee in {"short", "unsigned short"}:
                        t2 = self._new_temp()
                        self.instructions.append(IRInstruction(op="binop", result=t2, operand1=t, operand2="$65535", label="&"))
                        if pointee == "short":
                            t3 = self._new_temp()
                            self.instructions.append(IRInstruction(op="sext16", result=t3, operand1=t2))
                            t = t3
                        else:
                            t = t2
                self.instructions.append(IRInstruction(op="store", result=t, operand1=addr,
                                                       meta={"volatile": True} if _deref_vol else None))
                return t

            # handle pointer deref store: *p = rhs
            if expr.operator == "=" and isinstance(expr.target, UnaryOp) and expr.target.operator == "*":
                addr = self._gen_expr(expr.target.operand)
                # propagate pointer type from operand to the computed address
                try:
                    op_ty = getattr(self, "_var_types", {}).get(addr)
                    if not op_ty and isinstance(expr.target.operand, Identifier):
                        op_ty = getattr(self, "_var_types", {}).get(f"@{expr.target.operand.name}")
                    if isinstance(op_ty, str) and "*" in op_ty:
                        self._var_types[addr] = op_ty
                except Exception:
                    pass
                _deref_vol2 = self._is_volatile_deref(expr.target.operand)
                self.instructions.append(IRInstruction(op="store", result=rhs, operand1=addr,
                                                       meta={"volatile": True} if _deref_vol2 else None))
                return rhs
            # handle array element store: target is ArrayAccess
            if isinstance(expr.target, ArrayAccess):
                base = self._gen_expr(expr.target.array)
                idx = self._gen_expr(expr.target.index)
                # emit store_index with result carrying value temp
                self.instructions.append(IRInstruction(op="store_index", result=rhs, operand1=base, operand2=idx))
                return rhs

            # handle struct member store: target is MemberAccess
            if isinstance(expr.target, MemberAccess):
                base = self._gen_expr(expr.target.object)
                member = expr.target.member
                # Detect struct-to-struct member copy: if the member is a struct
                # type and the RHS is a dereference (*ptr), pass the pointer
                # address directly so codegen can use memcpy.
                meta_sm = {}
                rhs_val = rhs
                try:
                    if self._sema_ctx is not None:
                        bty = self._var_types.get(base, "")
                        if isinstance(bty, str) and bty.strip().endswith("*"):
                            bty = bty.strip()[:-1].strip()
                        resolved_bty = bty
                        seen_r = set()
                        while resolved_bty and resolved_bty not in seen_r:
                            if resolved_bty.startswith("struct ") or resolved_bty.startswith("union "):
                                break
                            seen_r.add(resolved_bty)
                            td = getattr(self._sema_ctx, "typedefs", {}).get(resolved_bty)
                            if td is None:
                                break
                            tb = getattr(td, "base", None)
                            if isinstance(tb, str):
                                resolved_bty = tb.strip()
                            else:
                                break
                        layout = getattr(self._sema_ctx, "layouts", {}).get(resolved_bty)
                        if layout is None:
                            layout = getattr(self._sema_ctx, "layouts", {}).get(bty)
                        if layout is not None:
                            mtypes = getattr(layout, "member_types", {}) or {}
                            mty = mtypes.get(member)
                            if isinstance(mty, str) and self._is_struct_or_union_type(mty):
                                meta_sm["struct_copy"] = True
                                # If the RHS was generated from *ptr (dereference),
                                # the last instruction is a load. Replace it with
                                # just the address.
                                if (self.instructions and
                                    self.instructions[-1].op == "load" and
                                    self.instructions[-1].result == rhs):
                                    src_addr = self.instructions[-1].operand1
                                    self.instructions.pop()
                                    rhs_val = src_addr
                except Exception:
                    pass
                # Annotate with member CType.
                sm_member_ct = self._lookup_member_ctype(base, member)
                if sm_member_ct is not None:
                    meta_sm["member_ctype"] = sm_member_ct
                # Compound assignment (e.g. s.val += n): load current value,
                # perform operation, then store back.
                if expr.operator != "=":
                    cur = self._new_temp()
                    load_meta = {"member_type": meta_sm.get("member_type", "")}
                    if sm_member_ct is not None:
                        load_meta["member_ctype"] = sm_member_ct
                    self.instructions.append(IRInstruction(
                        op="load_member", result=cur, operand1=base,
                        operand2=member, meta=load_meta, result_type=sm_member_ct))
                    bop = expr.operator[:-1]  # "+=" -> "+"
                    t = self._new_temp()
                    self.instructions.append(IRInstruction(
                        op="binop", result=t, operand1=cur, operand2=rhs_val, label=bop))
                    rhs_val = t
                self.instructions.append(IRInstruction(op="store_member", result=rhs_val, operand1=base, operand2=member, meta=meta_sm if meta_sm else None))
                return rhs

            if isinstance(expr.target, PointerMemberAccess):
                base = self._gen_expr(expr.target.pointer)
                member = expr.target.member
                meta = {}
                base_ty = self._var_types.get(base, "")
                if isinstance(base_ty, str) and base_ty.strip().endswith("*"):
                    struct_ty = base_ty.strip()[:-1].strip()
                    if struct_ty:
                        meta["struct_type"] = struct_ty
                # Detect struct-to-struct member copy via pointer
                rhs_val = rhs
                try:
                    if self._sema_ctx is not None and struct_ty:
                        resolved_sty = self._resolve_elem_type(struct_ty)
                        layout = getattr(self._sema_ctx, "layouts", {}).get(resolved_sty)
                        if layout is not None:
                            mtypes = getattr(layout, "member_types", {}) or {}
                            mty = mtypes.get(member)
                            if isinstance(mty, str) and self._is_struct_or_union_type(mty):
                                meta["struct_copy"] = True
                                if (self.instructions and
                                    self.instructions[-1].op == "load" and
                                    self.instructions[-1].result == rhs):
                                    src_addr = self.instructions[-1].operand1
                                    self.instructions.pop()
                                    rhs_val = src_addr
                except Exception:
                    pass
                # Annotate with member CType.
                smp_member_ct = self._lookup_member_ctype(base, member)
                if smp_member_ct is not None:
                    meta["member_ctype"] = smp_member_ct
                # Compound assignment (e.g. p->val += n): load current value,
                # perform operation, then store back.
                if expr.operator != "=":
                    cur = self._new_temp()
                    load_meta = {}
                    if meta.get("struct_type"):
                        load_meta["struct_type"] = meta["struct_type"]
                    if smp_member_ct is not None:
                        load_meta["member_ctype"] = smp_member_ct
                    self.instructions.append(IRInstruction(
                        op="load_member_ptr", result=cur, operand1=base,
                        operand2=member, meta=load_meta, result_type=smp_member_ct))
                    bop = expr.operator[:-1]  # "+=" -> "+"
                    t = self._new_temp()
                    self.instructions.append(IRInstruction(
                        op="binop", result=t, operand1=cur, operand2=rhs_val, label=bop))
                    rhs_val = t
                self.instructions.append(IRInstruction(op="store_member_ptr", result=rhs_val, operand1=base, operand2=member, meta=meta if meta else None))
                return rhs

            t = self._new_temp()
            self.instructions.append(IRInstruction(op="mov", result=t, operand1=rhs))
            return t
        if isinstance(expr, UnaryOp):
            # Special-case: `&array` should yield a pointer to the first element .
            # This makes `int (*p)[N]; p = &a;` usable as a subset (we treat it as `p = a`).
            if expr.operator == "&" and isinstance(expr.operand, Identifier):
                sym = f"@{expr.operand.name}"
                ty = getattr(self, "_var_types", {}).get(sym)
                if isinstance(ty, str) and ty.strip().startswith("array("):
                    t = self._new_temp()
                    self.instructions.append(IRInstruction(op="mov_addr", result=t, operand1=sym))
                    # type: decay array(T,$N) -> T*
                    inner = ty.strip()[len("array(") :]
                    if inner.endswith(")"):
                        inner = inner[:-1]
                    base_part = inner.split(",", 1)[0].strip()
                    getattr(self, "_var_types", {})[t] = f"{base_part}*"
                    return t

            # Dereference: treat as load from computed address.
            # Best-effort: use element type info from pointer operand when available.
            if expr.operator == "*":
                base = self._gen_expr(expr.operand)
                # propagate pointer type so codegen can choose correct width
                pointee_ty = None
                try:
                    op_ty = getattr(self, "_var_types", {}).get(base)
                    if not op_ty and isinstance(expr.operand, Identifier):
                        op_ty = getattr(self, "_var_types", {}).get(f"@{expr.operand.name}")
                    if isinstance(op_ty, str) and "*" in op_ty:
                        self._var_types[base] = op_ty
                        # Compute the type of the dereferenced value (peel one *)
                        stripped = op_ty.rstrip()
                        if stripped.endswith("*"):
                            pointee_ty = stripped[:-1].rstrip()
                except Exception:
                    pass
                # If the pointee is a struct/union, dereferencing produces an
                # lvalue (address), not a scalar load. Return the pointer as-is
                # so that downstream member access and struct-copy operations
                # can use it as a base address.
                if pointee_ty and self._is_struct_or_union_type(pointee_ty):
                    if pointee_ty:
                        self._var_types[base] = f"{pointee_ty}*"
                    return base
                # Also check via symbol table CType
                if self._sym_table:
                    base_ct = self._sym_table.lookup(base)
                    if isinstance(base_ct, PointerType) and base_ct.pointee is not None:
                        if base_ct.pointee.kind in (TypeKind.STRUCT, TypeKind.UNION):
                            return base
                t = self._new_temp()
                _deref_vol3 = self._is_volatile_deref(expr.operand)
                self.instructions.append(IRInstruction(op="load", result=t, operand1=base,
                                                       meta={"volatile": True} if _deref_vol3 else None))
                # Record the type of the loaded value for downstream ops
                if pointee_ty:
                    self._var_types[t] = pointee_ty
                return t

            # ++/-- operators
            if expr.operator in ("++", "--"):
                op_name = "+" if expr.operator == "++" else "-"
                # Determine step: 1 for integers, sizeof(pointee) for pointers
                delta = "$1"
                if isinstance(expr.operand, Identifier):
                    sym = self._resolve_name(expr.operand.name)
                    vty = self._var_types.get(sym, "")
                    if isinstance(vty, str) and "*" in vty:
                        base_ty = vty.split("*", 1)[0].strip()
                        step = self._sizeof(base_ty) if base_ty else 1
                        if step > 1:
                            delta = f"${step}"
                    _inc_vol = self._is_volatile_sym(sym)
                    old = self._new_temp()
                    self.instructions.append(IRInstruction(op="mov", result=old, operand1=sym,
                                                           meta={"volatile": True} if _inc_vol else None))
                    new = self._new_temp()
                    self.instructions.append(IRInstruction(op="binop", result=new, operand1=old, operand2=delta, label=op_name))
                    self.instructions.append(IRInstruction(op="mov", result=sym, operand1=new,
                                                           meta={"volatile": True} if _inc_vol else None))
                    return old if getattr(expr, "is_postfix", False) else new
                # MemberAccess: s.val++ / ++s.val / s.val-- / --s.val
                if isinstance(expr.operand, MemberAccess):
                    base = self._gen_expr(expr.operand.object)
                    member = expr.operand.member
                    member_ct = self._lookup_member_ctype(base, member)
                    load_meta = {"member_ctype": member_ct} if member_ct else {}
                    old = self._new_temp()
                    self.instructions.append(IRInstruction(
                        op="load_member", result=old, operand1=base,
                        operand2=member, meta=load_meta, result_type=member_ct))
                    new = self._new_temp()
                    self.instructions.append(IRInstruction(
                        op="binop", result=new, operand1=old, operand2=delta, label=op_name))
                    store_meta = {"member_ctype": member_ct} if member_ct else {}
                    self.instructions.append(IRInstruction(
                        op="store_member", result=new, operand1=base,
                        operand2=member, meta=store_meta))
                    return old if getattr(expr, "is_postfix", False) else new
                # PointerMemberAccess: p->val++ / ++p->val / p->val-- / --p->val
                if isinstance(expr.operand, PointerMemberAccess):
                    base = self._gen_expr(expr.operand.pointer)
                    member = expr.operand.member
                    member_ct = self._lookup_member_ctype(base, member)
                    load_meta = {"member_ctype": member_ct} if member_ct else {}
                    old = self._new_temp()
                    self.instructions.append(IRInstruction(
                        op="load_member_ptr", result=old, operand1=base,
                        operand2=member, meta=load_meta, result_type=member_ct))
                    new = self._new_temp()
                    self.instructions.append(IRInstruction(
                        op="binop", result=new, operand1=old, operand2=delta, label=op_name))
                    store_meta = {"member_ctype": member_ct} if member_ct else {}
                    self.instructions.append(IRInstruction(
                        op="store_member_ptr", result=new, operand1=base,
                        operand2=member, meta=store_meta))
                    return old if getattr(expr, "is_postfix", False) else new
                # Fallback for non-identifier operands (e.g. *p++)
                v = self._gen_expr(expr.operand)
                t = self._new_temp()
                self.instructions.append(IRInstruction(op="binop", result=t, operand1=v, operand2="$1", label=op_name))
                return v if getattr(expr, "is_postfix", False) else t

            v = self._gen_expr(expr.operand)
            t = self._new_temp()
            if expr.operator == "&":
                # address-of: only meaningful for identifiers/locals 
                self.instructions.append(IRInstruction(op="addr_of", result=t, operand1=v))
                # Best-effort: carry pointer type info for address temps so
                # codegen can emit correct `load/store` widths.
                try:
                    if isinstance(expr.operand, Identifier):
                        src_sym = f"@{expr.operand.name}"
                        src_ty = getattr(self, "_var_types", {}).get(src_sym)
                        if isinstance(src_ty, str) and not src_ty.strip().startswith("array("):
                            self._var_types[t] = f"{src_ty.strip()}*"
                except Exception:
                    pass
            else:
                # Float unary minus: emit fsub from zero
                if expr.operator == "-":
                    v_ty = self._var_types.get(v, "")
                    if isinstance(v_ty, str) and v_ty in ("float", "double", "long double"):
                        zero = self._new_temp()
                        self.instructions.append(IRInstruction(op="fmov", result=zero, operand1="0.0", meta={"fp_type": v_ty}))
                        self._var_types[zero] = v_ty
                        self.instructions.append(IRInstruction(op="fsub", result=t, operand1=zero, operand2=v, meta={"fp_type": v_ty}))
                        self._var_types[t] = v_ty
                        return t
                self.instructions.append(IRInstruction(op="unop", result=t, operand1=v, label=expr.operator))
            return t
        if isinstance(expr, BinaryOp):
            # Logical operators must be short-circuiting in C.
            if expr.operator in {"&&", "||"}:
                # Logical ops always produce int (0 or 1).
                _int_ct = IntegerType(kind=TypeKind.INT)
                out = self._new_temp_typed(_int_ct)

                l = self._gen_expr(expr.left)

                rhs_lbl = self._new_label(".Lsc_rhs")
                true_lbl = self._new_label(".Lsc_true")
                false_lbl = self._new_label(".Lsc_false")
                end_lbl = self._new_label(".Lsc_end")

                if expr.operator == "&&":
                    # if (!l) goto false; else eval r; if (!r) goto false; else goto true
                    self.instructions.append(IRInstruction(op="jz", operand1=l, label=false_lbl))
                    self.instructions.append(IRInstruction(op="label", label=rhs_lbl))
                    r = self._gen_expr(expr.right)
                    self.instructions.append(IRInstruction(op="jz", operand1=r, label=false_lbl))
                    self.instructions.append(IRInstruction(op="jmp", label=true_lbl))
                else:
                    # if (l) goto true; else eval r; if (r) goto true; else goto false
                    self.instructions.append(IRInstruction(op="jnz", operand1=l, label=true_lbl))
                    self.instructions.append(IRInstruction(op="label", label=rhs_lbl))
                    r = self._gen_expr(expr.right)
                    self.instructions.append(IRInstruction(op="jnz", operand1=r, label=true_lbl))
                    self.instructions.append(IRInstruction(op="jmp", label=false_lbl))

                self.instructions.append(IRInstruction(op="label", label=true_lbl))
                self.instructions.append(IRInstruction(op="mov", result=out, operand1="$1"))
                self.instructions.append(IRInstruction(op="jmp", label=end_lbl))
                self.instructions.append(IRInstruction(op="label", label=false_lbl))
                self.instructions.append(IRInstruction(op="mov", result=out, operand1="$0"))
                self.instructions.append(IRInstruction(op="label", label=end_lbl))
                return out

            l = self._gen_expr(expr.left)
            r = self._gen_expr(expr.right)

            # Float binary operations: emit float IR when either operand is float/double/long double
            lty_fp = self._var_types.get(l, "") if isinstance(l, str) else ""
            rty_fp = self._var_types.get(r, "") if isinstance(r, str) else ""
            _FP_TYPES_BIN = {"float", "double", "long double"}
            if lty_fp in _FP_TYPES_BIN or rty_fp in _FP_TYPES_BIN:
                # Determine common fp type: long double > double > float
                if "long double" in (lty_fp, rty_fp):
                    fp_type = "long double"
                elif "double" in (lty_fp, rty_fp):
                    fp_type = "double"
                else:
                    fp_type = "float"
                # Promote operands to common fp type
                if lty_fp not in _FP_TYPES_BIN:
                    conv = self._new_temp()
                    if fp_type == "float":
                        conv_op = "i2f"
                    elif fp_type == "long double":
                        conv_op = "i2ld"
                    else:
                        conv_op = "i2d"
                    self.instructions.append(IRInstruction(
                        op=conv_op,
                        result=conv, operand1=l, meta={"fp_type": fp_type}))
                    self._var_types[conv] = fp_type
                    l = conv
                elif lty_fp != fp_type:
                    conv = self._new_temp()
                    if lty_fp == "float" and fp_type == "double":
                        conv_op = "f2d"
                    elif lty_fp == "float" and fp_type == "long double":
                        conv_op = "f2ld"
                    elif lty_fp == "double" and fp_type == "long double":
                        conv_op = "d2ld"
                    else:
                        conv_op = "f2d"
                    self.instructions.append(IRInstruction(op=conv_op, result=conv, operand1=l, meta={"fp_type": fp_type}))
                    self._var_types[conv] = fp_type
                    l = conv
                if rty_fp not in _FP_TYPES_BIN:
                    conv = self._new_temp()
                    if fp_type == "float":
                        conv_op = "i2f"
                    elif fp_type == "long double":
                        conv_op = "i2ld"
                    else:
                        conv_op = "i2d"
                    self.instructions.append(IRInstruction(
                        op=conv_op,
                        result=conv, operand1=r, meta={"fp_type": fp_type}))
                    self._var_types[conv] = fp_type
                    r = conv
                elif rty_fp != fp_type:
                    conv = self._new_temp()
                    if rty_fp == "float" and fp_type == "double":
                        conv_op = "f2d"
                    elif rty_fp == "float" and fp_type == "long double":
                        conv_op = "f2ld"
                    elif rty_fp == "double" and fp_type == "long double":
                        conv_op = "d2ld"
                    else:
                        conv_op = "f2d"
                    self.instructions.append(IRInstruction(op=conv_op, result=conv, operand1=r, meta={"fp_type": fp_type}))
                    self._var_types[conv] = fp_type
                    r = conv
                # Determine CType for the float binary op result.
                if fp_type == "float":
                    _fbop_ct = FloatType(kind=TypeKind.FLOAT)
                else:
                    _fbop_ct = FloatType(kind=TypeKind.DOUBLE)
                t = self._new_temp_typed(_fbop_ct)
                meta = {"fp_type": fp_type}
                if expr.operator in {"+", "-", "*", "/"}:
                    fp_ops = {"+": "fadd", "-": "fsub", "*": "fmul", "/": "fdiv"}
                    self.instructions.append(IRInstruction(op=fp_ops[expr.operator], result=t, operand1=l, operand2=r, meta=meta))
                    self._var_types[t] = fp_type
                elif expr.operator in {"==", "!=", "<", "<=", ">", ">="}:
                    # Comparison result is always int, override the float CType.
                    if self._sym_table:
                        self._sym_table.insert(t, IntegerType(kind=TypeKind.INT))
                    self.instructions.append(IRInstruction(op="fcmp", result=t, operand1=l, operand2=r, label=expr.operator, meta=meta))
                    self._var_types[t] = "int"
                else:
                    self.instructions.append(IRInstruction(op="binop", result=t, operand1=l, operand2=r, label=expr.operator))
                return t

            # Integer promotions (C89): sign/zero-extend narrow types before ops
            def _materialize_int_promotion(opnd: str, ty: object) -> str:
                tyn = self._canon_int_type(ty)
                if tyn == "char":
                    s = self._new_temp()
                    self.instructions.append(IRInstruction(op="sext8", result=s, operand1=opnd))
                    self._var_types[s] = "int"
                    return s
                if tyn == "short":
                    s = self._new_temp()
                    self.instructions.append(IRInstruction(op="sext16", result=s, operand1=opnd))
                    self._var_types[s] = "int"
                    return s
                if tyn in {"unsigned char", "unsigned short"}:
                    s = self._new_temp()
                    self.instructions.append(IRInstruction(op="zext32", result=s, operand1=opnd))
                    self._var_types[s] = "int"  # value-range fits in int on this target
                    return s
                return opnd

            # Best-effort pointer arithmetic scaling: if one operand is a
            # pointer and the other is an integer, scale the integer by the
            # pointer's pointee size before add/sub.
            if expr.operator in {"+", "-"}:
                lty0 = getattr(self, "_var_types", {}).get(l)
                rty0 = getattr(self, "_var_types", {}).get(r)

                def _pointee_sz(ptr_ty: object) -> int:
                    """String-based fallback for pointee size."""
                    if not isinstance(ptr_ty, str) or "*" not in ptr_ty:
                        return 1
                    base = ptr_ty.split("*", 1)[0].strip()
                    # Use semantic layout for aggregates (e.g. `struct S*`).
                    if self._sema_ctx is not None:
                        try:
                            return _type_size_bytes(self._sema_ctx, base)
                        except Exception:
                            pass
                    return self._sizeof(base)

                def _resolve_ptr_scale(operand: str, str_ty: object) -> int:
                    """Resolve pointee element size: string primary, CType fallback.

                    During migration, casts update _var_types but not _sym_table
                    for named variables, so _var_types is more accurate after casts.
                    Use CType only when string path gives no useful result.
                    """
                    str_sz = _pointee_sz(str_ty)
                    if str_sz > 0 and str_sz != 1:
                        return str_sz
                    # String path gave 1 (char*) or failed; try CType.
                    ct_sz = self._pointee_size_from_ctype(operand)
                    if ct_sz is not None and ct_sz > 0:
                        # When string path returned 0 (failed completely, e.g.
                        # typedef or float/double pointee), always use CType.
                        # When string path returned 1 (char*), only override
                        # if string path had no pointer info at all.
                        if str_sz <= 0 or not isinstance(str_ty, str) or "*" not in str_ty:
                            return ct_sz
                    return str_sz

                # Detect which side is the pointer operand.
                l_is_ptr = (isinstance(lty0, str) and "*" in lty0) or self._lookup_pointer_ctype(l) is not None
                r_is_ptr = (isinstance(rty0, str) and "*" in rty0) or self._lookup_pointer_ctype(r) is not None

                if l_is_ptr and not r_is_ptr:
                    sz = _resolve_ptr_scale(l, lty0)
                    if sz != 1:
                        s = self._new_temp()
                        self.instructions.append(IRInstruction(op="binop", result=s, operand1=r, operand2=f"${sz}", label="*"))
                        r = s
                elif r_is_ptr and not l_is_ptr:
                    sz = _resolve_ptr_scale(r, rty0)
                    if sz != 1:
                        s = self._new_temp()
                        self.instructions.append(IRInstruction(op="binop", result=s, operand1=l, operand2=f"${sz}", label="*"))
                        l = s
            t = self._new_temp()

            if expr.operator in {"==", "!=", "<", "<=", ">", ">="}:
                # Comparison result is always int.
                if self._sym_table:
                    self._sym_table.insert(t, IntegerType(kind=TypeKind.INT))
                # Decide compare signedness based on the common type when known.
                lty = self._operand_type_string(l)
                rty = self._operand_type_string(r)
                unsigned = False
                if self._is_int_like_type(lty) and self._is_int_like_type(rty):
                    common = self._usual_arithmetic_conversion(lty, rty)
                    unsigned = common.startswith("unsigned ")
                    if common == "int":
                        l = _materialize_int_promotion(l, lty)
                        r = _materialize_int_promotion(r, rty)
                    elif common == "unsigned int":
                        # Ensure narrow unsigned values are zero-extended so
                        # codegen can reliably select a 32-bit unsigned compare.
                        l = _materialize_int_promotion(l, lty)
                        r = _materialize_int_promotion(r, rty)
                elif self._is_unsigned_operand(l) or self._is_unsigned_operand(r):
                    # Fallback for cases where one side is an untyped immediate.
                    unsigned = True
                cmp_op = f"u{expr.operator}" if unsigned else expr.operator
                self.instructions.append(IRInstruction(op="binop", result=t, operand1=l, operand2=r, label=cmp_op))
            else:
                # For arithmetic/bitwise ops, apply integer promotions up-front
                # so 64-bit ops don't accidentally treat narrow values as
                # already-extended (e.g. masked short temps).
                if expr.operator in {"+", "-", "*", "/", "%", "&", "|", "^", "<<", ">>"}:
                    lty = self._operand_type_string(l)
                    rty = self._operand_type_string(r)
                    if self._is_int_like_type(lty) and self._is_int_like_type(rty):
                        common = self._usual_arithmetic_conversion(lty, rty)
                        if common == "int":
                            l = _materialize_int_promotion(l, lty)
                            r = _materialize_int_promotion(r, rty)
                    # Register UAC result CType for arithmetic ops (non-pointer).
                    # Pointer type propagation is handled separately below.
                    if self._sym_table and expr.operator in {"+", "-", "*", "/", "%", "&", "|", "^", "<<", ">>"}:
                        _arith_ct = self._uac_result_ctype(
                            self._operand_type_string(l),
                            self._operand_type_string(r))
                        if _arith_ct is not None:
                            self._sym_table.insert(t, _arith_ct)
                self.instructions.append(IRInstruction(op="binop", result=t, operand1=l, operand2=r, label=expr.operator))

            # Best-effort: preserve pointer type when doing pointer +/- integer.
            # This is needed so later unary dereference or loads can interpret
            # the computed address correctly.
            if expr.operator in {"+", "-"}:
                lty = getattr(self, "_var_types", {}).get(l)
                rty = getattr(self, "_var_types", {}).get(r)
                if isinstance(lty, str) and "*" in lty and not (isinstance(rty, str) and "*" in rty):
                    self._var_types[t] = lty
                    # Also register in symbol table with the pointer CType.
                    lct = self._lookup_pointer_ctype(l)
                    if lct is not None and self._sym_table:
                        self._sym_table.insert(t, lct)
                elif isinstance(rty, str) and "*" in rty and not (isinstance(lty, str) and "*" in lty):
                    self._var_types[t] = rty
                    rct = self._lookup_pointer_ctype(r)
                    if rct is not None and self._sym_table:
                        self._sym_table.insert(t, rct)
                else:
                    # Neither side matched via string; try CType-only detection.
                    lct = self._lookup_pointer_ctype(l)
                    rct = self._lookup_pointer_ctype(r)
                    if lct is not None and rct is None and self._sym_table:
                        self._sym_table.insert(t, lct)
                    elif rct is not None and lct is None and self._sym_table:
                        self._sym_table.insert(t, rct)

            # Pointer difference (ptr - ptr) yields element count, not bytes.
            if expr.operator == "-":
                lty2 = getattr(self, "_var_types", {}).get(l)
                rty2 = getattr(self, "_var_types", {}).get(r)
                if isinstance(lty2, str) and "*" in lty2 and isinstance(rty2, str) and "*" in rty2:
                    # String-based path is primary (casts update _var_types
                    # but not _sym_table for named vars, so _var_types is
                    # more accurate after casts).
                    sz = self._sizeof(lty2.split("*", 1)[0].strip())
                    # Only use CType as fallback when string path gives 0.
                    if sz <= 0:
                        ct_sz = self._pointee_size_from_ctype(l)
                        if ct_sz is not None and ct_sz > 0:
                            sz = ct_sz
                    if sz > 1:
                        q = self._new_temp()
                        self.instructions.append(IRInstruction(op="binop", result=q, operand1=t, operand2=f"${sz}", label="/"))
                        return q
                else:
                    # CType-only path: both operands are pointers in symbol table
                    # but not recognized as pointers via _var_types strings.
                    lct2 = self._lookup_pointer_ctype(l)
                    rct2 = self._lookup_pointer_ctype(r)
                    if lct2 is not None and rct2 is not None:
                        ct_sz = self._pointee_size_from_ctype(l)
                        if ct_sz is not None and ct_sz > 1:
                            q = self._new_temp()
                            self.instructions.append(IRInstruction(op="binop", result=q, operand1=t, operand2=f"${ct_sz}", label="/"))
                            return q
            return t
        if isinstance(expr, FunctionCall):
            # Rewrite __builtin_foo(args) to c_library_equivalent(args).
            if isinstance(expr.function, Identifier):
                from pycc.builtins import get_c_library_name
                c_name = get_c_library_name(expr.function.name)
                if c_name is not None:
                    expr.function.name = c_name

            fn = self._gen_expr(expr.function)
            args = [self._gen_expr(a) for a in expr.arguments]
            t = self._new_temp()
            # Preserve best-effort function type for codegen (e.g. variadic
            # calls like printf need special ABI handling).
            call_ty = None
            # For now, only handle direct identifier calls (extern prototypes
            # are represented as global symbol types in sema).
            if call_ty is None and self._sema_ctx is not None and hasattr(expr.function, "name"):
                name = getattr(expr.function, "name")
                call_ty = getattr(self._sema_ctx, "global_types", {}).get(name)
            if call_ty is None:
                call_ty = getattr(self, "_var_types", {}).get(fn)

            # Ensure direct calls for known function identifiers. If the callee
            # was lowered as '@name' but semantics has no record, treat it as a
            # function symbol anyway (C89 implicit decl fallback).
            if isinstance(expr.function, Identifier):
                fn = f"@{expr.function.name}"

            # System-cpp header paths sometimes leave argument identifiers
            # as bare names (no '@' prefix). Ensure all identifier arguments
            # are treated as locals.
            try:
                fixed_args: list[str] = []
                for a in args:
                    if isinstance(a, str) and not a.startswith(("$", "@", "%", ".L")) and a.isidentifier():
                        fixed_args.append(f"@{a}")
                    else:
                        fixed_args.append(a)
                args = fixed_args
            except Exception:
                pass

            # Implicit int-to-double/float conversion for function call arguments.
            # When a prototype declares a parameter as double/float but the
            # actual argument is an integer, insert an i2d/i2f conversion.
            try:
                if self._sema_ctx is not None and isinstance(expr.function, Identifier):
                    param_types = getattr(self._sema_ctx, "function_param_types", {}).get(expr.function.name)
                    if param_types is not None:
                        _FP_PARAMS = {"float", "double", "long double"}
                        for pi in range(min(len(param_types), len(args))):
                            pt = str(param_types[pi]).strip().lower()
                            if pt not in _FP_PARAMS:
                                continue
                            # Check if the argument is already a float/double.
                            arg_ty = self._var_types.get(args[pi], "")
                            if isinstance(arg_ty, str) and arg_ty.strip().lower() in _FP_PARAMS:
                                continue
                            # Integer argument needs conversion to float/double.
                            if pt == "float":
                                conv_t = self._new_temp()
                                self._var_types[conv_t] = "float"
                                self.instructions.append(IRInstruction(
                                    op="i2f", result=conv_t, operand1=args[pi],
                                    meta={"fp_type": "float"},
                                    result_type=FloatType(kind=TypeKind.FLOAT)))
                                args[pi] = conv_t
                            else:
                                conv_t = self._new_temp()
                                self._var_types[conv_t] = "double"
                                self.instructions.append(IRInstruction(
                                    op="i2d", result=conv_t, operand1=args[pi],
                                    meta={"fp_type": "double"},
                                    result_type=FloatType(kind=TypeKind.DOUBLE)))
                                args[pi] = conv_t
            except Exception:
                pass

            self.instructions.append(IRInstruction(op="call", result=t, operand1=fn, operand2=str(call_ty) if call_ty is not None else None, args=args))
            # Register return type CType in symbol table for the call result temp.
            # Skip struct/union returns: the ABI uses a hidden pointer, so the
            # call result temp is not the struct value itself.
            if self._sym_table and isinstance(expr.function, Identifier):
                ret_ct = self._return_type_to_ctype(expr.function.name)
                if ret_ct is not None and ret_ct.kind not in (TypeKind.STRUCT, TypeKind.UNION):
                    self._sym_table.insert(t, ret_ct)
            # Record return type for float-aware codegen
            if isinstance(call_ty, str) and ("float" in call_ty or "double" in call_ty):
                ct = call_ty.strip()
                if ct.endswith("long double") or ct == "long double":
                    self._var_types[t] = "long double"
                elif ct.endswith("float"):
                    self._var_types[t] = "float"
                elif ct.endswith("double"):
                    self._var_types[t] = "double"
            return t
        if isinstance(expr, TernaryOp):
            t = self._new_temp()
            else_lbl = self._new_label(".Lternelse")
            end_lbl = self._new_label(".Lternend")

            # Best-effort: apply usual arithmetic conversions to the conditional
            # operator result for the limited unsigned tracking used by later
            # comparisons.
            tv = self._gen_expr(expr.true_expr)
            fv = self._gen_expr(expr.false_expr)
            # Use the operand type lookup helper so we also get declared
            # types for locals/globals (e.g. '@s' is 'short', not '').
            ty_tv = self._operand_type_string(tv)
            ty_fv = self._operand_type_string(fv)
            ty_tv_n = ty_tv.strip().lower() if isinstance(ty_tv, str) else ""
            ty_fv_n = ty_fv.strip().lower() if isinstance(ty_fv, str) else ""
            # Determine result type using the same usual arithmetic conversion
            # helper used by binary arithmetic/comparisons (integer-only subset).
            try:
                if self._is_int_like_type(ty_tv) and self._is_int_like_type(ty_fv):
                    common = self._usual_arithmetic_conversion(ty_tv, ty_fv)
                    if isinstance(common, str) and common:
                        self._var_types[t] = common
            except Exception:
                pass

            # If the usual arithmetic conversion decided on int/unsigned int,
            # materialize promotions on the *arms* right away.
            # Otherwise the selected value can carry a masked 16-bit form into
            # later comparisons and force unsigned condition codes.
            res_ty = getattr(self, "_var_types", {}).get(t, "")
            res_ty_n = res_ty.strip().lower() if isinstance(res_ty, str) else ""

            # Materialize integer promotions for `?:` when the common type is
            # int. This fixes cases where one arm is a masked short temp that
            # later compares as positive without sign-extension.
            def _materialize_int_promotion(opnd: str, ty: object) -> str:
                tyn = self._canon_int_type(ty)
                if tyn == "char":
                    s = self._new_temp()
                    self.instructions.append(IRInstruction(op="sext8", result=s, operand1=opnd))
                    self._var_types[s] = "int"
                    return s
                if tyn == "short":
                    s = self._new_temp()
                    self.instructions.append(IRInstruction(op="sext16", result=s, operand1=opnd))
                    self._var_types[s] = "int"
                    return s
                if tyn in {"unsigned char", "unsigned short"}:
                    s = self._new_temp()
                    self.instructions.append(IRInstruction(op="zext32", result=s, operand1=opnd))
                    # Integer promotions for unsigned short/char yield an
                    # unsigned int in our model.
                    self._var_types[s] = "unsigned int"
                    return s
                return opnd

            if res_ty_n in {"int", "unsigned int"}:
                tv = _materialize_int_promotion(tv, ty_tv)
                fv = _materialize_int_promotion(fv, ty_fv)

            # IMPORTANT: Don't override the computed common type here.
            # `unsigned short` and `short` both integer-promote to `int` on
            # this target, so the conditional operator result is `int`.
            # The previous code tried to special-case this but was inverted
            # and could force unsigned compares.

            # If the result is unsigned long, preserve unsignedness for later
            # comparisons. (No width change on x86-64; this is just type info.)
            res_ty = getattr(self, "_var_types", {}).get(t, "")
            res_ty_n = res_ty.strip().lower() if isinstance(res_ty, str) else ""
            if res_ty_n.startswith("unsigned long"):
                self._var_types[t] = "unsigned long"

            # If the result is unsigned int, ensure both arms are zero-extended
            # to 64-bit so that negative int values behave like UINT_MAX, etc.
            if res_ty_n.startswith("unsigned int"):
                tv2 = self._new_temp()
                fv2 = self._new_temp()
                self._var_types[tv2] = "unsigned int"
                self._var_types[fv2] = "unsigned int"
                self.instructions.append(IRInstruction(op="zext32", result=tv2, operand1=tv))
                self.instructions.append(IRInstruction(op="zext32", result=fv2, operand1=fv))
                tv, fv = tv2, fv2

            c = self._gen_expr(expr.condition)
            self.instructions.append(IRInstruction(op="jz", operand1=c, label=else_lbl))
            self.instructions.append(IRInstruction(op="mov", result=t, operand1=tv))
            self.instructions.append(IRInstruction(op="jmp", label=end_lbl))
            self.instructions.append(IRInstruction(op="label", label=else_lbl))
            self.instructions.append(IRInstruction(op="mov", result=t, operand1=fv))
            self.instructions.append(IRInstruction(op="label", label=end_lbl))
            return t

        if isinstance(expr, CommaOp):
            # Evaluate left for side-effects, discard value, then evaluate right.
            self._gen_expr(expr.left)
            return self._gen_expr(expr.right)

        # fallback
        t = self._new_temp()
        self.instructions.append(IRInstruction(op="mov", result=t, operand1="$0"))
        return t
