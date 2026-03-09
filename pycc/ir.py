"""pycc.ir

Intermediate Representation (IR) for AuraCompiler.

This project originally planned a full TAC-based middle-end. To keep progress
incremental, this module now provides a *minimal* IR that is still a list of
instructions, but is tailored to the current code generator implementation.

IR is organized as a list of `IRInstruction` plus a few container records:

- `func_begin` / `func_end`
- `label`, `jmp`, `jz`
- `mov`, `binop`, `call`, `ret`

Operands are simple strings (temporaries like %t0, locals like @x, immediates
like $5, and labels like .L1). The code generator will interpret them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Union, Any

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
    CharLiteral,
    Statement,
    Expression,
)


class IRGenError(Exception):
    pass


def _eval_const_int_expr(expr: Expression) -> int:
    """Evaluate a minimal integer constant expression (C89 subset).

    Used for switch case labels (and similar contexts) at IR-generation time.
    """

    if isinstance(expr, IntLiteral):
        return int(expr.value)
    if isinstance(expr, CharLiteral):
        return ord(expr.value)
    if isinstance(expr, UnaryOp) and expr.operator in {"+", "-", "~"}:
        v = _eval_const_int_expr(expr.operand)
        if expr.operator == "+":
            return v
        if expr.operator == "-":
            return -v
        return ~v
    if isinstance(expr, BinaryOp) and expr.operator in {"+", "-", "*", "/", "%", "|", "&", "^", "<<", ">>"}:
        l = _eval_const_int_expr(expr.left)
        r = _eval_const_int_expr(expr.right)
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
    if isinstance(expr, CommaOp):
        _eval_const_int_expr(expr.left)
        return _eval_const_int_expr(expr.right)

    if isinstance(expr, TernaryOp):
        cond = _eval_const_int_expr(expr.condition)
        if cond != 0:
            return _eval_const_int_expr(expr.true_expr)
        return _eval_const_int_expr(expr.false_expr)

    raise IRGenError("not an integer constant expression")


def _type_size(ty: Optional[object]) -> int:
    """Best-effort sizeof for the current project stage.

    Returns byte size for builtin integers/pointers and for the stringly-typed
    forms used by the rest of the compiler (e.g. "long int").
    """

    if ty is None:
        return 8
    # Allow passing stringly-typed types like "int", "char", "unsigned int".
    if isinstance(ty, str):
        b = " ".join(ty.strip().split())
        if "*" in b:
            return 8
        if b in {"char", "unsigned char", "signed char"}:
            return 1
        if b in {"short", "short int", "unsigned short", "unsigned short int", "signed short", "signed short int"}:
            return 2
        if b in {"int", "unsigned int", "signed int"} or b.startswith("enum "):
            return 4
        if b in {"long", "long int", "unsigned long", "unsigned long int", "signed long", "signed long int"}:
            return 8
        return 8

    # Type node
    base = getattr(ty, "base", None)
    if isinstance(base, str):
        if getattr(ty, "is_pointer", False):
            return 8
        b = " ".join(base.strip().split())
        if b == "char" or b == "unsigned char" or b == "signed char":
            return 1
        if b in {"short int", "short", "unsigned short", "unsigned short int", "signed short", "signed short int"}:
            return 2
        if b == "int" or b == "unsigned int" or b == "signed int":
            return 4
        if b in {"long int", "long", "unsigned long", "unsigned long int", "signed long", "signed long int"}:
            return 8
        # treat enums as int
        if b.startswith("enum "):
            return 4
    # fallback
    return 8


def _type_align(ty: Optional[object]) -> int:
    """Best-effort alignment for the current project stage (x86-64 SysV).

    This is used for padding when packing constant initializer blobs for
    structs/unions.
    """

    if ty is None:
        return 8
    if isinstance(ty, str):
        b = ty.strip()
        if "*" in b:
            return 8
        if b in {"char", "unsigned char", "signed char"}:
            return 1
        if b in {"short", "short int", "unsigned short", "unsigned short int", "signed short", "signed short int"}:
            return 2
        if b in {"int", "unsigned int", "signed int"} or b.startswith("enum "):
            return 4
        if b in {"long", "long int", "unsigned long", "unsigned long int", "signed long", "signed long int"}:
            return 8
        # default
        return 8

    base = getattr(ty, "base", None)
    if isinstance(base, str):
        if getattr(ty, "is_pointer", False):
            return 8
        b = base.strip()
        if b in {"char", "unsigned char", "signed char"}:
            return 1
        if b in {"short int", "short", "unsigned short", "unsigned short int", "signed short", "signed short int"}:
            return 2
        if b in {"int", "unsigned int", "signed int"} or b.startswith("enum "):
            return 4
        if b in {"long int", "long", "unsigned long", "unsigned long int", "signed long", "signed long int"}:
            return 8
    return 8


def _type_size_bytes(sema_ctx: object, ty: Optional[object]) -> int:
    """Best-effort size (bytes) for constant-initializer packing."""
    if ty is None:
        return 0
    if isinstance(ty, str):
        b = ty.strip()
        if b.startswith("struct ") or b.startswith("union "):
            layout = getattr(sema_ctx, "layouts", {}).get(b)
            return int(getattr(layout, "size", 0) or 0) if layout is not None else 0
        if "*" in b:
            return 8
        if b in {"char", "unsigned char", "signed char"}:
            return 1
        if b in {"short", "short int", "unsigned short", "unsigned short int", "signed short", "signed short int"}:
            return 2
        if b in {"int", "unsigned int", "signed int"} or b.startswith("enum "):
            return 4
        if b in {"long", "long int", "unsigned long", "unsigned long int", "signed long", "signed long int"}:
            return 8
        if "long long" in b:
            return 8
        return 0

    # Type node
    kind = getattr(ty, "kind", None)
    if kind in ("struct", "union"):
        layout = getattr(sema_ctx, "layouts", {}).get(str(ty))
        return int(getattr(layout, "size", 0) or 0) if layout is not None else 0
    if kind == "pointer" or getattr(ty, "is_pointer", False):
        return 8
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

    def __post_init__(self) -> None:
        if self.args is None:
            self.args = []


class IRGenerator:
    """Generates intermediate representation (3-Address Code)"""
    
    def __init__(self):
        self.instructions: List[IRInstruction] = []
        self.temp_counter = 0
        self.label_counter = 0
        self._break_stack: List[str] = []
        self._continue_stack: List[str] = []
        self._sema_ctx = None
    
    def generate(self, ast: Program) -> List[IRInstruction]:
        """Generate IR from AST"""
        self.instructions = []
        self.temp_counter = 0
        self.label_counter = 0
        self._break_stack = []
        self._continue_stack = []

        # Enum constants are compile-time integers; record them so Identifier
        # lowering can replace them with immediates.
        self._enum_constants: dict[str, int] = {}
        # Track local array symbols per function to implement array-to-pointer decay.
        self._local_arrays: set[str] = set()
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
                            label=sc,
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
                        if imm is None and ptr is None:
                            raise Exception(
                                f"unsupported global initializer for {decl.name}: only integer/char constants and string-literal pointers supported"
                            )
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
            s = " ".join(ty.strip().lower().split())
        else:
            try:
                s = " ".join(str(ty).strip().lower().split())
            except Exception:
                return ""

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
        if isinstance(decl.type, ArrayType):
            base = str(getattr(decl.type.element_type, "base", base))
        # Arrays: represented by decl.array_size (parser doesn't always wrap type).
        # Also handle unsized arrays (`T a[] = {...}`) by inferring element count
        # from the initializer list.
        is_array_decl = (
            isinstance(decl.type, ArrayType)
            or getattr(decl, "array_size", None) is not None
            or (
                # Parser encodes `T a[]` as base type T with array_size=None.
                # Treat it as an array only for supported global initializers:
                # - char/int arrays
                # - array of structs/unions (nested Initializer lists)
                getattr(decl, "array_size", None) is None
                and isinstance(init, Initializer)
                and (
                    # Only treat a struct/union as an unsized array if the
                    # initializer is nested (i.e., looks like {{...},{...}}).
                    (self._is_struct_or_union_type(base) and any(isinstance(x, Initializer) for x in (self._const_initializer_list(init) or [])))
                    or str(base).strip() in {"char", "unsigned char", "int", "unsigned int"}
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
            if elem_base in {"char", "unsigned char"}:
                # string literal init
                inits = self._const_initializer_list(init)
                if inits is not None and len(inits) == 1 and isinstance(inits[0], StringLiteral):
                    s = inits[0].value
                    bytes_vals = [ord(c) for c in s]
                    if len(bytes_vals) < n:
                        bytes_vals.append(0)
                    if len(bytes_vals) > n:
                        bytes_vals = bytes_vals[:n]
                    if len(bytes_vals) < n:
                        bytes_vals = bytes_vals + [0] * (n - len(bytes_vals))
                    return "blob:" + "".join(f"{b & 0xFF:02x}" for b in bytes_vals)

                # brace list of scalar consts
                inits = self._const_initializer_list(init)
                if inits is None:
                    return None
                vals: list[int] = []
                for e in inits[:n]:
                    imm = self._const_expr_to_int(e)
                    if imm is None:
                        return None
                    vals.append(imm & 0xFF)
                if len(vals) < n:
                    vals += [0] * (n - len(vals))
                return "blob:" + "".join(f"{b:02x}" for b in vals)

            if elem_base == "int" or elem_base == "unsigned int":
                inits = self._const_initializer_list(init)
                if inits is None:
                    return None
                vals: list[int] = []
                for e in inits[:n]:
                    imm = self._const_expr_to_int(e)
                    if imm is None:
                        return None
                    # store as 32-bit little endian
                    v = imm & 0xFFFFFFFF
                    vals.extend([(v >> (8 * i)) & 0xFF for i in range(4)])
                # zero-fill remaining
                rem = n - min(n, len(inits))
                if rem > 0:
                    vals.extend([0] * (4 * rem))
                return "blob:" + "".join(f"{b:02x}" for b in vals)

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
            inits = self._const_initializer_list(init)
            if inits is None:
                return None
            if self._sema_ctx is None:
                return None
            layout = getattr(self._sema_ctx, "layouts", {}).get(str(base))
            if layout is None:
                return None

            size = int(getattr(layout, "size", 0))
            blob = bytearray([0] * size)

            members = list(getattr(layout, "member_offsets", {}).keys())
            offsets = getattr(layout, "member_offsets", {})
            sizes = getattr(layout, "member_sizes", {})

            # If semantics doesn't encode padding (e.g. offsets are 0,4 for two ints
            # but struct size is 16), fall back to ABI-like packing using member_types.
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
                    if midx >= len(inits):
                        break
                    mty = mtypes.get(m)
                    if not isinstance(mty, str):
                        return None
                    align = _type_align(mty)
                    sz = _type_size(mty)
                    if align > 1:
                        pad = (-cur) % align
                        if pad:
                            out.extend(b"\x00" * pad)
                            cur += pad
                    imm = self._const_expr_to_int(inits[midx])
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
            for midx, m in enumerate(members):
                if midx >= len(inits):
                    break
                imm = self._const_expr_to_int(inits[midx])
                if imm is None:
                    return None
                off = int(offsets.get(m, 0))
                sz = int(sizes.get(m, 4))
                v = int(imm)
                for i in range(min(sz, 8)):
                    if off + i < len(blob):
                        blob[off + i] = (v >> (8 * i)) & 0xFF

            return "blob:" + blob.hex()

        return None

    def _const_expr_to_int(self, expr: Any) -> Optional[int]:
        """Best-effort const int evaluator (subset)."""
        if expr is None:
            return None
        if isinstance(expr, IntLiteral):
            return int(expr.value)
        if isinstance(expr, CharLiteral):
            return ord(expr.value)
        if isinstance(expr, UnaryOp) and expr.operator in {"+", "-"}:
            v = self._const_expr_to_int(expr.operand)
            if v is None:
                return None
            return v if expr.operator == "+" else -v
        return None

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

        This is currently used only for *local* aggregate initialization.
        Global aggregates are deferred to a later milestone.
        """

        if isinstance(init, Initializer):
            return [e for (_d, e) in (init.elements or [])]
        # Allow `char s[] = "..."` to be treated like an initializer-list with one element.
        # The parser currently represents this as a plain StringLiteral expression.
        if isinstance(init, StringLiteral):
            return [init]
        return None

    # -------------
    # Helpers
    # -------------

    def _new_temp(self) -> str:
        t = f"%t{self.temp_counter}"
        self.temp_counter += 1
        return t

    def _new_label(self, prefix: str = ".L") -> str:
        l = f"{prefix}{self.label_counter}"
        self.label_counter += 1
        return l

    def _is_struct_or_union_type(self, base: object) -> bool:
        if not isinstance(base, str):
            return False
        b = base.strip()
        return b.startswith("struct ") or b.startswith("union ")

    def _lower_local_struct_initializer(self, decl: Declaration) -> bool:
        """Lower `struct/union T x = { ... }` for local variables (subset).

        Subset:
        - non-designated initializer list
        - direct fields only (no nested aggregates)
        - remaining fields are zero-filled

        Returns True if handled.
        """

        if decl.initializer is None:
            return False
        if not self._is_struct_or_union_type(decl.type.base):
            return False
        if not isinstance(decl.initializer, Initializer):
            return False
        if self._sema_ctx is None:
            return False

        layout = getattr(self._sema_ctx, "layouts", {}).get(str(decl.type.base))
        if layout is None:
            return False

        # Preserve declared type on the symbol so codegen can resolve member offsets/sizes.
        self._var_types[f"@{decl.name}"] = str(decl.type.base)

        # Parse initializer list elements in order (designators unsupported here).
        elems = [e for (_d, e) in (decl.initializer.elements or [])]
        members = list(layout.member_offsets.keys())

        for i, m in enumerate(members):
            val_expr = elems[i] if i < len(elems) else IntLiteral(value=0, is_hex=False, is_octal=False, line=decl.line, column=decl.column)
            v = self._gen_expr(val_expr)
            # Use store_member; codegen consults semantic layout for offset/size.
            self.instructions.append(IRInstruction(op="store_member", result=v, operand1=f"@{decl.name}", operand2=m))
        return True

    # -------------
    # Functions
    # -------------

    def _gen_function(self, fn: FunctionDecl) -> None:
        self._fn_name = fn.name
        # Best-effort: function return type string for ABI-sensitive returns.
        # FunctionDecl uses `.return_type` in this codebase.
        try:
            rt0 = getattr(fn, "return_type", "")
            rt_base = getattr(rt0, "base", rt0)
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
        self._var_types: dict[str, str] = {}
        # Function-local static storage (lowered to global symbols).
        # Maps source name -> global symbol name (without leading '@').
        self._local_static_syms: dict[str, str] = {}
        def _ty_str(t) -> str:
            # Encode pointer-ness in the type string so codegen doesn't
            # accidentally spill pointer args using 8/16/32-bit stores.
            # (Our type system is still stringly-typed in later stages.)
            base = str(getattr(t, "base", ""))
            # Preserve full struct/union tag spelling.
            try:
                if isinstance(base, str) and (base.strip().startswith("struct ") or base.strip().startswith("union ")):
                    base = base.strip()
            except Exception:
                pass
            if getattr(t, "is_pointer", False):
                return f"{base}*"
            return base

        # params are treated as locals; codegen will map them from ABI regs
        for p in fn.parameters:
            ty_s = _ty_str(p.type)
            self._var_types[f"@{p.name}"] = ty_s
            self.instructions.append(IRInstruction(op="param", result=f"@{p.name}", operand1=ty_s))
        self._gen_stmt(fn.body)
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

    # -------------
    # Statements
    # -------------

    def _gen_stmt(self, stmt: Statement) -> None:
        if isinstance(stmt, CompoundStmt):
            for item in stmt.statements:
                if isinstance(item, Declaration):
                    # Local static variables: lower to a unique global symbol so state persists.
                    if getattr(item, "storage_class", None) == "static":
                        self._ensure_local_static_aliases()
                        gname = f"__local_static_{self._current_function_name()}_{item.name}_{self.label_counter}"
                        self.label_counter += 1
                        self._local_static_syms[item.name] = gname

                        # Define storage once, with constant initializer if present.
                        if getattr(item, "initializer", None) is None:
                            self.instructions.append(IRInstruction(op="gdef", result=f"@{gname}", operand1=item.type.base, operand2="$0", label="static"))
                        else:
                            imm = self._const_initializer_imm(item.initializer)
                            ptr = self._const_initializer_ptr(item.initializer)
                            if imm is None and ptr is None:
                                raise Exception(
                                    f"unsupported local static initializer for {item.name}: only integer/char constants and string-literal pointers supported"
                                )
                            self.instructions.append(
                                IRInstruction(
                                    op="gdef",
                                    result=f"@{gname}",
                                    operand1=item.type.base,
                                    operand2=imm if imm is not None else ptr,
                                    label="static",
                                )
                            )

                        # Record type for the lowered global symbol.
                        self._var_types[f"@{gname}"] = str(item.type.base)

                        # If initializer exists, we already applied it at global init time.
                        # Skip normal local decl/init lowering.
                        continue

                    # If this is an array with known size, encode element count in operand1.
                    # Also support C89: `char s[] = "..."` (size inferred from string literal).
                    op1 = None
                    if getattr(item, "array_size", None) is not None:
                        op1 = f"array({item.type.base},${item.array_size})"
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

                    # If this is an array with known/inferred size, record it
                    # as an array type even when element type is struct/union.
                    if op1 is not None:
                        self.instructions.append(IRInstruction(op="decl", result=f"@{item.name}", operand1=op1))
                        self._local_arrays.add(item.name)
                        self._var_types[f"@{item.name}"] = str(op1)
                    elif self._is_struct_or_union_type(item.type.base):
                        decl_op1 = str(item.type.base)
                        self.instructions.append(IRInstruction(op="decl", result=f"@{item.name}", operand1=decl_op1))
                        self._var_types[f"@{item.name}"] = decl_op1
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
                                if decl_base.startswith("struct ") or decl_base.startswith("union "):
                                    decl_op1 = f"{decl_base}*"
                                else:
                                    decl_op1 = f"{decl_op1}*"
                            self.instructions.append(IRInstruction(op="decl", result=f"@{item.name}", operand1=decl_op1))
                            self._var_types[f"@{item.name}"] = str(decl_op1)

                    # Local struct/union brace init (subset)
                    # If this is a pointer variable, record its declared pointee
                    # type so pointer arithmetic can scale correctly.
                    try:
                        if getattr(item.type, "is_pointer", False):
                            base = str(getattr(item.type, "base", "")).strip()
                            if base:
                                self._var_types[f"@{item.name}"] = f"{base}*"
                    except Exception:
                        pass
                    if self._lower_local_struct_initializer(item):
                        continue
                    if item.initializer is not None:
                        # Fixed-size char array string initializer: `char s[N] = "hi";`
                        # Must be lowered as byte stores, not via generic int-array init.
                        if item.type.base in {"char", "unsigned char"} and getattr(item, "array_size", None) is not None:
                            inits = self._const_initializer_list(item.initializer)
                            if inits is not None and len(inits) == 1 and isinstance(inits[0], StringLiteral):
                                s = inits[0].value
                                n = int(item.array_size)
                                bytes_vals = [ord(c) for c in s]
                                if len(bytes_vals) < n:
                                    bytes_vals.append(0)
                                if len(bytes_vals) > n:
                                    bytes_vals = bytes_vals[:n]
                                else:
                                    bytes_vals = bytes_vals + [0] * (n - len(bytes_vals))
                                for idx, b in enumerate(bytes_vals):
                                    self.instructions.append(
                                        IRInstruction(
                                            op="store_index",
                                            result=f"${b}",
                                            operand1=f"@{item.name}",
                                            operand2=f"${idx}",
                                            label="char",
                                        )
                                    )
                                continue

                        # Local aggregate initialization for arrays.
                        if getattr(item, "array_size", None) is not None:
                            inits = self._const_initializer_list(item.initializer)
                            if inits is None:
                                raise Exception("unsupported array initializer: expected initializer list")

                            # int a[N] = {...}
                            n = int(item.array_size)
                            for idx in range(n):
                                val_ast = inits[idx] if idx < len(inits) else IntLiteral(
                                    value=0,
                                    is_hex=False,
                                    is_octal=False,
                                    line=item.line,
                                    column=item.column,
                                )
                                v = self._gen_expr(val_ast)
                                self.instructions.append(
                                    IRInstruction(
                                        op="store_index",
                                        result=v,
                                        operand1=f"@{item.name}",
                                        operand2=f"${idx}",
                                        label="int",
                                    )
                                )
                            continue

                        # char s[] = "abc"; (C89)
                        if item.type.base in {"char", "unsigned char"} and getattr(item, "array_size", None) is None:
                            inits = self._const_initializer_list(item.initializer)
                            if inits is not None and len(inits) == 1 and isinstance(inits[0], StringLiteral):
                                s = inits[0].value
                                bytes_vals = [ord(c) for c in s] + [0]
                                for idx, b in enumerate(bytes_vals):
                                    self.instructions.append(
                                        IRInstruction(
                                            op="store_index",
                                            result=f"${b}",
                                            operand1=f"@{item.name}",
                                            operand2=f"${idx}",
                                            label="char",
                                        )
                                    )
                                continue

                        # int a[N] = {...} (or any array base we don't support specially)
                        # already handled above when `array_size` is known.
                        # If we reached here and this is an array, it means we don't
                        # support the given initializer form for arrays yet.
                        if getattr(item, "array_size", None) is not None:
                            raise Exception("unsupported array initializer")

                        # Scalar init (existing path)
                        v = self._gen_expr(item.initializer)
                        self.instructions.append(IRInstruction(op="mov", result=f"@{item.name}", operand1=v))
                else:
                    self._gen_stmt(item)
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
                        cvi = _eval_const_int_expr(it.value)
                    except IRGenError:
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
            # C labels are function-scoped. Lower to a plain IR label.
            self.instructions.append(IRInstruction(op="label", label=f".Luser_{stmt.name}"))
            self._gen_stmt(stmt.statement)
            return

        if isinstance(stmt, GotoStmt):
            self.instructions.append(IRInstruction(op="jmp", label=f".Luser_{stmt.label}"))
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

    # -------------
    # Expressions
    # -------------

    def _gen_expr(self, expr: Expression) -> str:
        if isinstance(expr, IntLiteral):
            return f"${expr.value}"
        if isinstance(expr, CharLiteral):
            # In C, character constants have type int.
            # Our AST stores the raw single-character string.
            return f"${ord(expr.value)}"
        if isinstance(expr, StringLiteral):
            t = self._new_temp()
            # encode string in IR as str_const with result temp
            self.instructions.append(IRInstruction(op="str_const", result=t, operand1=expr.value))
            # Record that this temp is a pointer (char*).
            self._var_types[t] = "char*"
            return t
        if isinstance(expr, SizeOf):
            # For now, lower sizeof to an immediate constant as best-effort.
            # Semantics/type-checking will be extended later; this supports core C89 tests.
            if expr.type is not None:
                return f"${_type_size(expr.type)}"
            # sizeof(expression): handle a few common expression shapes.
            op = expr.operand
            if op is None:
                return "$8"
            # If semantics has already attached a type to the operand
            # expression, use it.
            try:
                op_ty = getattr(op, "type", None)
                if op_ty is not None:
                    return f"${_type_size(op_ty)}"
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
                        n = 1
                        if cnt_part.startswith("$"):
                            try:
                                n = int(cnt_part[1:])
                            except Exception:
                                n = 1
                        return f"${_type_size(base_part) * max(0, n)}"
                # Use declared local/global type when available.
                ty_s = self._operand_type_string(f"@{op.name}")
                if isinstance(ty_s, str) and ty_s:
                    return f"${_type_size(ty_s)}"
                # fallback
                return "$4"
            if isinstance(op, ASTUnaryOp) and op.operator == "*":
                # sizeof(*p) == sizeof(pointee)
                base = op.operand
                if isinstance(base, ASTIdentifier):
                    pty = self._operand_type_string(f"@{base.name}")
                    if isinstance(pty, str) and "*" in pty:
                        return f"${_type_size(pty.split('*', 1)[0].strip())}"
            if isinstance(op, ASTArrayAccess):
                # element size: int arrays are 4, char* indexing is 1. Default to 4.
                return "$4"
            if isinstance(op, (ASTMemberAccess, ASTPointerMemberAccess)):
                return "$4"
            # fallback
            return "$4"

        if isinstance(expr, Cast):
            # MVP: keep casts as value-preserving for ints/pointers.
            # This is enough for common C89 patterns like `(int*)0`, `(char)65`.
            v = self._gen_expr(expr.expression)
            # Best-effort: record cast destination type for later signedness decisions.
            try:
                dst_ty = getattr(expr, "type", None)
                dst_str = str(dst_ty) if dst_ty is not None else None
            except Exception:
                dst_ty = None
                dst_str = None
            if isinstance(dst_str, str):
                # Narrow integer casts must truncate/extend, otherwise expressions like
                # `(unsigned char)x` won't behave correctly (e.g. after a sign-extended
                # byte load).
                # Normalize spaces to make downstream string checks stable.
                dst_norm = " ".join(dst_str.strip().lower().split())
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
                if dst_norm in {"unsigned char", "char"} and not getattr(dst_ty, "is_pointer", False):
                    # Truncate to 8 bits (zero-extend on read by masking).
                    t = self._new_temp()
                    self.instructions.append(IRInstruction(op="binop", result=t, operand1=v, operand2="$255", label="&"))
                    self._var_types[t] = dst_str
                    v = t
                elif dst_norm == "signed char":
                    # Truncate to 8 bits then sign-extend back to the IR's
                    # working width.
                    #
                    # This is required for cases like:
                    #   x == (signed char)-116
                    # where the RHS constant must compare as -116, not 140.
                    t = self._new_temp()
                    self.instructions.append(IRInstruction(op="binop", result=t, operand1=v, operand2="$255", label="&"))
                    t2 = self._new_temp()
                    self.instructions.append(IRInstruction(op="sext8", result=t2, operand1=t))
                    self._var_types[t2] = dst_str
                    v = t2
                elif dst_norm in {"unsigned short", "unsigned short int", "short", "short int"} and not getattr(dst_ty, "is_pointer", False):
                    # Truncate to 16 bits.
                    # For signed `short`, also sign-extend so comparisons use
                    # the same representation as loads (which are sign-extended).
                    t = self._new_temp()
                    self.instructions.append(IRInstruction(op="binop", result=t, operand1=v, operand2="$65535", label="&"))
                    dst_canon = self._canon_int_type(dst_str)
                    self._var_types[t] = dst_canon
                    if dst_canon == "short":
                        t2 = self._new_temp()
                        self.instructions.append(IRInstruction(op="sext16", result=t2, operand1=t))
                        self._var_types[t2] = "short"
                        v = t2
                    else:
                        v = t
                elif dst_norm in {"signed short", "signed short int"} and not getattr(dst_ty, "is_pointer", False):
                    # Truncate to 16 bits then sign-extend.
                    t = self._new_temp()
                    self.instructions.append(IRInstruction(op="binop", result=t, operand1=v, operand2="$65535", label="&"))
                    t2 = self._new_temp()
                    self.instructions.append(IRInstruction(op="sext16", result=t2, operand1=t))
                    self._var_types[t2] = self._canon_int_type(dst_str)
                    v = t2
                # Preserve pointer-ness in casted values.
                if getattr(dst_ty, "is_pointer", False):
                    # Keep pointer type spelling stable for downstream codegen.
                    if "*" in dst_str:
                        self._var_types[v] = dst_str
                    else:
                        self._var_types[v] = f"{dst_str}*"
                else:
                    self._var_types[v] = dst_str
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

            sym = f"@{expr.name}"
            # Array-to-pointer decay in rvalue context: emit explicit addr-of.
            # Our semantic/type system is minimal; detect arrays by the presence of
            # a declared array_size on the declaration node (recorded earlier by decl).
            # Since IR is stringly-typed, we conservatively treat any symbol that was
            # declared as an array in this function as decaying to its address.
            # NOTE: `self._local_arrays` stores plain names (without '@').
            if hasattr(self, "_local_arrays") and expr.name in getattr(self, "_local_arrays"):
                t = self._new_temp()
                self.instructions.append(IRInstruction(op="mov_addr", result=t, operand1=sym))
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
                return t
            # If this identifier is known to be a pointer variable, preserve
            # its type on the symbol reference so later ops (ptr arith, loads)
            # can make sizing decisions.
            try:
                ty = getattr(self, "_var_types", {}).get(sym)
                if isinstance(ty, str):
                    self._var_types[sym] = ty
            except Exception:
                pass
            return sym
        if isinstance(expr, FunctionDecl):
            # Function designator in expression context decays to a function
            # pointer; represent it as a direct symbol reference.
            return f"@{expr.name}"
        if isinstance(expr, MemberAccess):
            base = self._gen_expr(expr.object)
            t = self._new_temp()
            self.instructions.append(
                IRInstruction(op="load_member", result=t, operand1=base, operand2=expr.member)
            )
            return t
        # Address-of a member: &obj.member
        if isinstance(expr, UnaryOp) and expr.operator == "&" and isinstance(expr.operand, MemberAccess):
            ma = expr.operand
            base = self._gen_expr(ma.object)
            t = self._new_temp()
            self.instructions.append(IRInstruction(op="addr_of_member", result=t, operand1=base, operand2=ma.member))
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
        if isinstance(expr, ArrayAccess):
            base = self._gen_expr(expr.array)
            idx = self._gen_expr(expr.index)
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
                        return taddr
            except Exception:
                pass

            t = self._new_temp()
            self.instructions.append(IRInstruction(op="load_index", result=t, operand1=base, operand2=idx))
            return t
        if isinstance(expr, PointerMemberAccess):
            base = self._gen_expr(expr.pointer)
            t = self._new_temp()
            self.instructions.append(IRInstruction(op="load_member_ptr", result=t, operand1=base, operand2=expr.member))
            return t
        if isinstance(expr, Assignment):
            rhs = self._gen_expr(expr.value)
            # only handle identifier targets in MVP
            if isinstance(expr.target, Identifier):
                # local statics lower to unique global symbols
                if hasattr(self, "_local_static_syms") and expr.target.name in getattr(self, "_local_static_syms", {}):
                    dst = f"@{self._local_static_syms[expr.target.name]}"
                else:
                    dst = f"@{expr.target.name}"
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
                    self.instructions.append(IRInstruction(op="mov", result=dst, operand1=rhs))
                    return dst
                # compound assigns: a += b => a = a + b
                cur = self._gen_expr(expr.target)
                bop = expr.operator[:-1]

                # Best-effort pointer compound arithmetic scaling.
                # If `cur` is a pointer and rhs is integer, scale rhs by pointee size.
                cty = getattr(self, "_var_types", {}).get(cur)
                rty = getattr(self, "_var_types", {}).get(rhs)
                if bop in {"+", "-"} and isinstance(cty, str) and "*" in cty and not (isinstance(rty, str) and "*" in rty):
                    sz = _type_size(cty.split("*", 1)[0].strip())
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
                self.instructions.append(IRInstruction(op="mov", result=dst, operand1=t))
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
                self.instructions.append(IRInstruction(op="load", result=cur, operand1=addr))

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
                if bop in {"+", "-"} and isinstance(cty, str) and "*" in cty and not (
                    isinstance(rty, str) and "*" in rty
                ):
                    sz = _type_size(cty.split("*", 1)[0].strip())
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
                self.instructions.append(IRInstruction(op="store", result=t, operand1=addr))
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
                self.instructions.append(IRInstruction(op="store", result=rhs, operand1=addr))
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
                self.instructions.append(IRInstruction(op="store_member", result=rhs, operand1=base, operand2=expr.target.member))
                return rhs

            if isinstance(expr.target, PointerMemberAccess):
                base = self._gen_expr(expr.target.pointer)
                self.instructions.append(IRInstruction(op="store_member_ptr", result=rhs, operand1=base, operand2=expr.target.member))
                return rhs

            t = self._new_temp()
            self.instructions.append(IRInstruction(op="mov", result=t, operand1=rhs))
            return t
        if isinstance(expr, UnaryOp):
            # Special-case: `&array` should yield a pointer to the first element in this MVP.
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
                try:
                    op_ty = getattr(self, "_var_types", {}).get(base)
                    if not op_ty and isinstance(expr.operand, Identifier):
                        op_ty = getattr(self, "_var_types", {}).get(f"@{expr.operand.name}")
                    if isinstance(op_ty, str) and "*" in op_ty:
                        self._var_types[base] = op_ty
                except Exception:
                    pass
                t = self._new_temp()
                self.instructions.append(IRInstruction(op="load", result=t, operand1=base))
                return t

            v = self._gen_expr(expr.operand)
            t = self._new_temp()
            if expr.operator == "&":
                # address-of: only meaningful for identifiers/locals in MVP
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
                self.instructions.append(IRInstruction(op="unop", result=t, operand1=v, label=expr.operator))
            return t
        if isinstance(expr, BinaryOp):
            # Logical operators must be short-circuiting in C.
            if expr.operator in {"&&", "||"}:
                out = self._new_temp()

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

            # Materialize integer promotions (C89): many operations promote
            # smaller integer types (char/short) to int (or unsigned int).
            # Our codegen executes ops in 64-bit, so we must explicitly
            # sign/zero-extend masked/narrow temps to preserve semantics.
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
                    if not isinstance(ptr_ty, str) or "*" not in ptr_ty:
                        return 1
                    base = ptr_ty.split("*", 1)[0].strip()
                    # Use semantic layout for aggregates (e.g. `struct S*`).
                    if self._sema_ctx is not None:
                        try:
                            return _type_size_bytes(self._sema_ctx, base)
                        except Exception:
                            pass
                    return _type_size(base)

                if isinstance(lty0, str) and "*" in lty0 and not (isinstance(rty0, str) and "*" in rty0):
                    sz = _pointee_sz(lty0)
                    if sz != 1:
                        s = self._new_temp()
                        self.instructions.append(IRInstruction(op="binop", result=s, operand1=r, operand2=f"${sz}", label="*"))
                        r = s
                elif isinstance(rty0, str) and "*" in rty0 and not (isinstance(lty0, str) and "*" in lty0):
                    sz = _pointee_sz(rty0)
                    if sz != 1:
                        s = self._new_temp()
                        self.instructions.append(IRInstruction(op="binop", result=s, operand1=l, operand2=f"${sz}", label="*"))
                        l = s
            t = self._new_temp()

            if expr.operator in {"==", "!=", "<", "<=", ">", ">="}:
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
                self.instructions.append(IRInstruction(op="binop", result=t, operand1=l, operand2=r, label=expr.operator))

            # Best-effort: preserve pointer type when doing pointer +/- integer.
            # This is needed so later unary dereference or loads can interpret
            # the computed address correctly.
            if expr.operator in {"+", "-"}:
                lty = getattr(self, "_var_types", {}).get(l)
                rty = getattr(self, "_var_types", {}).get(r)
                if isinstance(lty, str) and "*" in lty and not (isinstance(rty, str) and "*" in rty):
                    self._var_types[t] = lty
                elif isinstance(rty, str) and "*" in rty and not (isinstance(lty, str) and "*" in lty):
                    self._var_types[t] = rty

            # Pointer difference (ptr - ptr) yields element count, not bytes.
            if expr.operator == "-":
                lty2 = getattr(self, "_var_types", {}).get(l)
                rty2 = getattr(self, "_var_types", {}).get(r)
                if isinstance(lty2, str) and "*" in lty2 and isinstance(rty2, str) and "*" in rty2:
                    # assume compatible pointee types; semantic layer may further restrict
                    sz = _type_size(lty2.split("*", 1)[0].strip())
                    if sz > 1:
                        q = self._new_temp()
                        self.instructions.append(IRInstruction(op="binop", result=q, operand1=t, operand2=f"${sz}", label="/"))
                        return q
            return t
        if isinstance(expr, FunctionCall):
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

            self.instructions.append(IRInstruction(op="call", result=t, operand1=fn, operand2=str(call_ty) if call_ty is not None else None, args=args))
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
