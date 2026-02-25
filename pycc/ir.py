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
    Assignment,
    FunctionCall,
    ArrayAccess,
    MemberAccess,
    PointerMemberAccess,
    TernaryOp,
    SizeOf,
    Cast,
    Initializer,
    CharLiteral,
    Statement,
    Expression,
)


def _type_size(ty: Optional[object]) -> int:
    """Best-effort sizeof for the current project stage.

    Returns byte size for builtin integers/pointers and for the stringly-typed
    forms used by the rest of the compiler (e.g. "long int").
    """

    if ty is None:
        return 8
    # Type node
    base = getattr(ty, "base", None)
    if isinstance(base, str):
        if getattr(ty, "is_pointer", False):
            return 8
        b = base.strip()
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

    def _const_initializer_imm(self, init: Any) -> Optional[str]:
        """Return an immediate like "$42" for supported constant initializers."""
        from pycc.ast_nodes import IntLiteral, CharLiteral, UnaryOp

        if isinstance(init, IntLiteral):
            return f"${int(init.value)}"
        if isinstance(init, CharLiteral):
            # CharLiteral.value is a single-character string (e.g. "h").
            # Use its code point as the integer value.
            return f"${ord(init.value)}"
        if isinstance(init, UnaryOp) and init.op in {"+", "-"}:
            inner = self._const_initializer_imm(init.operand)
            if inner is None:
                return None
            v = int(inner.lstrip("$"))
            if init.op == "-":
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

    # -------------
    # Functions
    # -------------

    def _gen_function(self, fn: FunctionDecl) -> None:
        self.instructions.append(IRInstruction(op="func_begin", label=fn.name))
        # reset per-function array set
        self._local_arrays = set()
        # Track declared types of locals/params for signedness decisions.
        self._var_types: dict[str, str] = {}
        # params are treated as locals; codegen will map them from ABI regs
        for p in fn.parameters:
            self._var_types[f"@{p.name}"] = str(p.type.base)
            self.instructions.append(IRInstruction(op="param", result=f"@{p.name}", operand1=p.type.base))
        self._gen_stmt(fn.body)
        # Ensure a return exists
        self.instructions.append(IRInstruction(op="ret", operand1="$0"))
        self.instructions.append(IRInstruction(op="func_end", label=fn.name))

    # -------------
    # Statements
    # -------------

    def _gen_stmt(self, stmt: Statement) -> None:
        if isinstance(stmt, CompoundStmt):
            for item in stmt.statements:
                if isinstance(item, Declaration):
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

                    if op1 is not None:
                        self.instructions.append(IRInstruction(op="decl", result=f"@{item.name}", operand1=op1))
                        self._local_arrays.add(item.name)
                        self._var_types[f"@{item.name}"] = str(op1)
                    else:
                        # Infer `T[]` element count from brace initializer.
                        # e.g. `int a[] = {1,2,3};`
                        if getattr(item, "array_size", None) is None and item.initializer is not None:
                            inits0 = self._const_initializer_list(item.initializer)
                            if inits0 is not None and isinstance(item.type.base, str) and item.type.base in {"int", "char", "unsigned char"}:
                                # Only support a flat initializer list of scalar constants here.
                                if all(isinstance(e, (IntLiteral, CharLiteral, UnaryOp)) for e in inits0):
                                    n0 = len(inits0)
                                    op1 = f"array({item.type.base},${n0})"
                                    self.instructions.append(IRInstruction(op="decl", result=f"@{item.name}", operand1=op1))
                                    self._local_arrays.add(item.name)
                                    self._var_types[f"@{item.name}"] = str(op1)
                                    # Populate so later store_index lowering knows N.
                                    try:
                                        item.array_size = n0
                                    except Exception:
                                        pass
                                else:
                                    op1 = None
                        if op1 is None:
                            # scalar local
                            op1 = item.type.base
                            if getattr(item.type, "is_pointer", False):
                                op1 = f"{op1}*"
                            self.instructions.append(IRInstruction(op="decl", result=f"@{item.name}", operand1=op1))
                            self._var_types[f"@{item.name}"] = str(op1)
                    if item.initializer is not None:
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
            for it in flat:
                if isinstance(it, CaseStmt):
                    case_entries.append((it, self._new_label(".Lcase")))
                elif isinstance(it, DefaultStmt):
                    default_lbl = self._new_label(".Ldefault")

            dispatch_default = default_lbl if default_lbl is not None else end

            # Dispatch chain.
            for c, lbl in case_entries:
                cv = self._gen_expr(c.value)
                t = self._new_temp()
                self.instructions.append(IRInstruction(op="binop", result=t, operand1=sw, operand2=cv, label="=="))
                self.instructions.append(IRInstruction(op="jnz", operand1=t, label=lbl))
            self.instructions.append(IRInstruction(op="jmp", label=dispatch_default))

            # Emit the linear body stream.
            # - Declarations inside the switch compound allocate locals as usual.
            # - `case`/`default` emit labels, then continue emitting subsequent statements.
            # Pre-compute identity-based mapping for labels.
            case_label_by_id = {id(c): lbl for (c, lbl) in case_entries}

            for it in flat:
                if isinstance(it, Declaration):
                    # IMPORTANT: locals in IR use the "@" prefix for codegen.
                    if getattr(it, "array_size", None) is not None:
                        self.instructions.append(
                            IRInstruction(op="decl", result=f"@{it.name}", operand1=f"array({it.type.base},${it.array_size})")
                        )
                        self._local_arrays.add(it.name)
                    else:
                        op1 = it.type.base
                        if getattr(it.type, "is_pointer", False):
                            op1 = f"{op1}*"
                        self.instructions.append(IRInstruction(op="decl", result=f"@{it.name}", operand1=op1))
                    if it.initializer is not None:
                        v = self._gen_expr(it.initializer)
                        self.instructions.append(IRInstruction(op="mov", result=f"@{it.name}", operand1=v))
                    continue

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
            from pycc.ast_nodes import (
                Identifier as ASTIdentifier,
                ArrayAccess as ASTArrayAccess,
                MemberAccess as ASTMemberAccess,
                PointerMemberAccess as ASTPointerMemberAccess,
            )
            if isinstance(op, ASTIdentifier):
                # Without full typing in IR, assume int.
                return "$4"
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
                dst_ty = getattr(expr, "to_type", None)
                dst_str = getattr(dst_ty, "base", None) if dst_ty is not None else None
            except Exception:
                dst_str = None
            if isinstance(dst_str, str):
                self._var_types[v] = dst_str
            # If casting to pointer, allow integer literal 0 to stay 0; otherwise passthrough.
            return v
        if isinstance(expr, Identifier):
            # enum constants lower to immediates
            if hasattr(self, "_enum_constants") and expr.name in self._enum_constants:
                return f"${self._enum_constants[expr.name]}"
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
        if isinstance(expr, ArrayAccess):
            base = self._gen_expr(expr.array)
            idx = self._gen_expr(expr.index)
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
                dst = f"@{expr.target.name}"
                if expr.operator == "=":
                    self.instructions.append(IRInstruction(op="mov", result=dst, operand1=rhs))
                    return dst
                # compound assigns: a += b => a = a + b
                cur = self._gen_expr(expr.target)
                t = self._new_temp()
                bop = expr.operator[:-1]
                self.instructions.append(IRInstruction(op="binop", result=t, operand1=cur, operand2=rhs, label=bop))
                self.instructions.append(IRInstruction(op="mov", result=dst, operand1=t))
                return dst
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
            v = self._gen_expr(expr.operand)
            t = self._new_temp()
            if expr.operator == "&":
                # address-of: only meaningful for identifiers/locals in MVP
                self.instructions.append(IRInstruction(op="addr_of", result=t, operand1=v))
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
            t = self._new_temp()
            if expr.operator in {"==", "!=", "<", "<=", ">", ">="}:
                # Preserve comparison signedness in IR (best-effort) so codegen
                # doesn't need full typing. If either operand is unsigned, use
                # unsigned condition codes.
                unsigned = self._is_unsigned_operand(l) or self._is_unsigned_operand(r)
                cmp_op = f"u{expr.operator}" if unsigned else expr.operator
                self.instructions.append(IRInstruction(op="binop", result=t, operand1=l, operand2=r, label=cmp_op))
            else:
                self.instructions.append(IRInstruction(op="binop", result=t, operand1=l, operand2=r, label=expr.operator))
            return t
        if isinstance(expr, FunctionCall):
            fn = self._gen_expr(expr.function)
            args = [self._gen_expr(a) for a in expr.arguments]
            t = self._new_temp()
            self.instructions.append(IRInstruction(op="call", result=t, operand1=fn, args=args))
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
            ty_tv = getattr(self, "_var_types", {}).get(tv, "")
            ty_fv = getattr(self, "_var_types", {}).get(fv, "")
            ty_tv_n = ty_tv.strip().lower() if isinstance(ty_tv, str) else ""
            ty_fv_n = ty_fv.strip().lower() if isinstance(ty_fv, str) else ""
            if self._is_unsigned_operand(tv) or self._is_unsigned_operand(fv):
                # Pick a representative unsigned type to help later comparisons.
                # Prefer unsigned long if either side is unsigned long.
                if ty_tv_n.startswith("unsigned long") or ty_fv_n.startswith("unsigned long"):
                    self._var_types[t] = "unsigned long"
                else:
                    self._var_types[t] = "unsigned int"
            elif (ty_tv_n.startswith("long") and ty_fv_n.startswith("unsigned long")) or (
                ty_tv_n.startswith("unsigned long") and ty_fv_n.startswith("long")
            ):
                # Usual arithmetic conversions: long vs unsigned long -> unsigned long.
                self._var_types[t] = "unsigned long"

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

        # fallback
        t = self._new_temp()
        self.instructions.append(IRInstruction(op="mov", result=t, operand1="$0"))
        return t
