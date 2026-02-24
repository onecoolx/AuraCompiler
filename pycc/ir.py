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
from typing import List, Optional, Union

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
    ReturnStmt,
    BreakStmt,
    ContinueStmt,
    Identifier,
    IntLiteral,
    StringLiteral,
    BinaryOp,
    UnaryOp,
    Assignment,
    FunctionCall,
    ArrayAccess,
    TernaryOp,
    Statement,
    Expression,
)


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

        for decl in ast.declarations:
            if isinstance(decl, FunctionDecl) and decl.body is not None:
                self._gen_function(decl)
            elif isinstance(decl, Declaration):
                # global vars not supported in MVP (ignore)
                pass
        return self.instructions

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
        # params are treated as locals; codegen will map them from ABI regs
        for p in fn.parameters:
            self.instructions.append(IRInstruction(op="param", result=f"@{p.name}"))
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
                    # If this is an array with known size, encode element count in operand1
                    if getattr(item, "array_size", None) is not None:
                        self.instructions.append(IRInstruction(op="decl", result=f"@{item.name}", operand1=f"${item.array_size}"))
                    else:
                        self.instructions.append(IRInstruction(op="decl", result=f"@{item.name}"))
                    if item.initializer is not None:
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
        if isinstance(expr, StringLiteral):
            t = self._new_temp()
            # encode string in IR as str_const with result temp
            self.instructions.append(IRInstruction(op="str_const", result=t, operand1=expr.value))
            return t
        if isinstance(expr, Identifier):
            return f"@{expr.name}"
        if isinstance(expr, ArrayAccess):
            base = self._gen_expr(expr.array)
            idx = self._gen_expr(expr.index)
            t = self._new_temp()
            self.instructions.append(IRInstruction(op="load_index", result=t, operand1=base, operand2=idx))
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

            t = self._new_temp()
            self.instructions.append(IRInstruction(op="mov", result=t, operand1=rhs))
            return t
        if isinstance(expr, UnaryOp):
            v = self._gen_expr(expr.operand)
            t = self._new_temp()
            self.instructions.append(IRInstruction(op="unop", result=t, operand1=v, label=expr.operator))
            return t
        if isinstance(expr, BinaryOp):
            l = self._gen_expr(expr.left)
            r = self._gen_expr(expr.right)
            t = self._new_temp()
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
            c = self._gen_expr(expr.condition)
            self.instructions.append(IRInstruction(op="jz", operand1=c, label=else_lbl))
            tv = self._gen_expr(expr.true_expr)
            self.instructions.append(IRInstruction(op="mov", result=t, operand1=tv))
            self.instructions.append(IRInstruction(op="jmp", label=end_lbl))
            self.instructions.append(IRInstruction(op="label", label=else_lbl))
            fv = self._gen_expr(expr.false_expr)
            self.instructions.append(IRInstruction(op="mov", result=t, operand1=fv))
            self.instructions.append(IRInstruction(op="label", label=end_lbl))
            return t

        # fallback
        t = self._new_temp()
        self.instructions.append(IRInstruction(op="mov", result=t, operand1="$0"))
        return t
