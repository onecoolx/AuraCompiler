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
from typing import Dict, List, Optional, Set, Union

from pycc.ast_nodes import (
        Program,
        Declaration,
        FunctionDecl,
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
)


class SemanticError(Exception):
    """Semantic analysis error"""
    pass


class SemanticAnalyzer:
    """Semantic analyzer for C99"""
    
    def __init__(self):
        # A simple scope stack: list of dict(name -> kind)
        self._scopes: List[Dict[str, str]] = [{}]
        self.errors: List[str] = []
        self.warnings: List[str] = []
        # Track globally known functions (including implicit decls)
        self._functions: Set[str] = set()
    
    def analyze(self, ast: Program) -> bool:
        """Analyze AST for semantic errors"""
        self.errors = []
        self.warnings = []
        self._scopes = [{}]
        self._functions = set()

        for decl in ast.declarations:
            if isinstance(decl, FunctionDecl):
                self._declare_global(decl.name, "function")
                self._functions.add(decl.name)
            elif isinstance(decl, Declaration):
                self._declare_global(decl.name, "variable")

        for decl in ast.declarations:
            if isinstance(decl, FunctionDecl) and decl.body is not None:
                self._analyze_function(decl)
            elif isinstance(decl, Declaration) and decl.initializer is not None:
                self._analyze_expr(decl.initializer)

        if self.errors:
            raise SemanticError("\n".join(self.errors))
        return True

    # -----------------
    # Scopes
    # -----------------

    def _push_scope(self) -> None:
        self._scopes.append({})

    def _pop_scope(self) -> None:
        self._scopes.pop()

    def _declare_global(self, name: str, kind: str) -> None:
        if name in self._scopes[0]:
            self.errors.append(f"Duplicate global declaration: {name}")
        else:
            self._scopes[0][name] = kind

    def _declare_local(self, name: str, kind: str) -> None:
        if name in self._scopes[-1]:
            self.errors.append(f"Duplicate declaration in scope: {name}")
        else:
            self._scopes[-1][name] = kind

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
        for p in fn.parameters:
            self._declare_local(p.name, "param")
        self._analyze_stmt(fn.body)
        self._pop_scope()

    def _analyze_stmt(self, stmt: Statement) -> None:
        if isinstance(stmt, CompoundStmt):
            self._push_scope()
            for item in stmt.statements:
                if isinstance(item, Declaration):
                    self._declare_local(item.name, "variable")
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

        # Unknown statement types are ignored for now

    def _analyze_expr(self, expr: Expression) -> None:
        if isinstance(expr, (IntLiteral, StringLiteral, CharLiteral)):
            return

        if isinstance(expr, Identifier):
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
