"""
Abstract Syntax Tree (AST) Node Definitions for C99 Compiler

Defines the structure of AST nodes used to represent C99 programs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Union, Any


@dataclass
class ASTNode:
    """Base class for all AST nodes"""
    # Location fields (line/column) are required constructor arguments
    # so subclasses' non-default fields don't follow defaults.
    line: int
    column: int


# ============== Type Nodes ==============

@dataclass
class Type(ASTNode):
    """Represents a C type"""
    base: str  # 'int', 'float', 'char', 'void', 'struct', 'union', etc.
    is_pointer: bool = False
    is_const: bool = False
    is_volatile: bool = False
    is_restrict: bool = False
    is_unsigned: bool = False
    is_signed: bool = False
    
    def __str__(self) -> str:
        result = ""
        if self.is_const:
            result += "const "
        if self.is_volatile:
            result += "volatile "
        if self.is_restrict:
            result += "restrict "
        if self.is_unsigned:
            result += "unsigned "
        if self.is_signed:
            result += "signed "
        result += self.base
        if self.is_pointer:
            result += " *"
        return result

    @property
    def is_array(self) -> bool:
        # Parser encodes arrays via Declaration.array_size; the Type itself
        # remains the element type. Keep this as a conservative default.
        return False


@dataclass
class ArrayType(ASTNode):
    """Array type"""
    element_type: 'Type'
    size: Optional['Expression'] = None  # None for unsized or VLA
    is_static: bool = False
    qualifiers: List[str] = field(default_factory=list)  # const, volatile, etc.


@dataclass
class PointerType(ASTNode):
    """Pointer type"""
    pointed_type: 'Type'
    qualifiers: List[str] = field(default_factory=list)


@dataclass
class FunctionType(ASTNode):
    """Function type"""
    return_type: 'Type'
    parameters: List['Declaration']
    is_variadic: bool = False


# ============== Declaration Nodes ==============

@dataclass
class Declaration(ASTNode):
    """Variable or parameter declaration"""
    name: str
    type: Type
    initializer: Optional['Expression'] = None
    storage_class: Optional[str] = None  # 'auto', 'static', 'extern', 'register'
    is_typedef: bool = False
    # For array declarators: number of elements (int) when known
    array_size: Optional[int] = None


@dataclass
class FunctionDecl(ASTNode):
    """Function declaration/definition"""
    name: str
    return_type: Type
    parameters: List[Declaration]
    body: Optional['Statement'] = None  # None if only declaration
    is_variadic: bool = False
    storage_class: Optional[str] = None  # 'extern', 'static'
    is_inline: bool = False


@dataclass
class StructDecl(ASTNode):
    """Structure declaration"""
    name: Optional[str]
    members: Optional[List[Declaration]] = None  # None if only name (forward decl)


@dataclass
class UnionDecl(ASTNode):
    """Union declaration"""
    name: Optional[str]
    members: Optional[List[Declaration]] = None


@dataclass
class TypedefDecl(ASTNode):
    """Typedef declaration"""
    name: str
    type: Type


@dataclass
class EnumDecl(ASTNode):
    """Enum declaration"""
    name: Optional[str]
    enumerators: Optional[List[tuple[str, Optional['Expression']]]] = None


# ============== Statement Nodes ==============

@dataclass
class Statement(ASTNode):
    """Base class for statements"""
    pass


@dataclass
class CompoundStmt(Statement):
    """Block statement { ... }"""
    statements: List[Union[Statement, Declaration]] = field(default_factory=list)


@dataclass
class ExpressionStmt(Statement):
    """Expression statement"""
    expression: Optional['Expression'] = None


@dataclass
class IfStmt(Statement):
    """If statement"""
    condition: 'Expression'
    then_stmt: Statement
    else_stmt: Optional[Statement] = None


@dataclass
class WhileStmt(Statement):
    """While loop"""
    condition: 'Expression'
    body: Statement


@dataclass
class DoWhileStmt(Statement):
    """Do-while loop"""
    body: Statement
    condition: 'Expression'


@dataclass
class ForStmt(Statement):
    """For loop"""
    init: Optional[Union['Expression', Declaration]] = None
    condition: Optional['Expression'] = None
    update: Optional['Expression'] = None
    body: Optional[Statement] = None


@dataclass
class SwitchStmt(Statement):
    """Switch statement"""
    expression: 'Expression'
    body: Statement


@dataclass
class CaseStmt(Statement):
    """Case label in switch"""
    value: 'Expression'
    statement: Statement


@dataclass
class DefaultStmt(Statement):
    """Default label in switch"""
    statement: Statement


@dataclass
class BreakStmt(Statement):
    """Break statement"""
    pass


@dataclass
class ContinueStmt(Statement):
    """Continue statement"""
    pass


@dataclass
class ReturnStmt(Statement):
    """Return statement"""
    value: Optional['Expression'] = None


@dataclass
class GotoStmt(Statement):
    """Goto statement"""
    label: str


@dataclass
class LabelStmt(Statement):
    """Label statement"""
    name: str
    statement: Statement


@dataclass
class DeclStmt(Statement):
    """Declaration statement"""
    declaration: Declaration


# ============== Expression Nodes ==============

@dataclass
class Expression(ASTNode):
    """Base class for expressions"""
    pass


@dataclass
class Identifier(Expression):
    """Identifier (variable or function name)"""
    name: str


@dataclass
class IntLiteral(Expression):
    """Integer literal"""
    value: int
    is_hex: bool = False
    is_octal: bool = False


@dataclass
class FloatLiteral(Expression):
    """Float literal"""
    value: float


@dataclass
class CharLiteral(Expression):
    """Character literal"""
    value: str  # Single character


@dataclass
class StringLiteral(Expression):
    """String literal"""
    value: str


@dataclass
class BinaryOp(Expression):
    """Binary operation"""
    operator: str  # '+', '-', '*', '/', '%', '==', '!=', '<', '>', etc.
    left: Expression
    right: Expression


@dataclass
class UnaryOp(Expression):
    """Unary operation"""
    operator: str  # '+', '-', '!', '~', '*', '&', '++', '--', 'sizeof'
    operand: Expression
    is_postfix: bool = False


@dataclass
class TernaryOp(Expression):
    """Ternary conditional operation (? :)"""
    condition: Expression
    true_expr: Expression
    false_expr: Expression


@dataclass
class CommaOp(Expression):
    """Comma operator: evaluates left, discards its value, then evaluates right."""

    left: Expression
    right: Expression


@dataclass
class Assignment(Expression):
    """Assignment expression"""
    target: Expression
    operator: str  # '=', '+=', '-=', '*=', '/=', '%=', etc.
    value: Expression


@dataclass
class FunctionCall(Expression):
    """Function call"""
    function: Expression  # Usually an Identifier
    arguments: List[Expression]


@dataclass
class ArrayAccess(Expression):
    """Array indexing"""
    array: Expression
    index: Expression


@dataclass
class MemberAccess(Expression):
    """Struct/union member access (.)"""
    object: Expression
    member: str


@dataclass
class PointerMemberAccess(Expression):
    """Struct/union member access through pointer (->)"""
    pointer: Expression
    member: str


@dataclass
class Cast(Expression):
    """Type cast"""
    type: Type
    expression: Expression


@dataclass
class SizeOf(Expression):
    """Sizeof operator"""
    operand: Optional[Expression] = None  # None if sizeof(type)
    type: Optional[Type] = None


@dataclass
class AlignOf(Expression):
    """Alignof operator (_Alignof)"""
    operand: Optional[Expression] = None
    type: Optional[Type] = None


@dataclass
class Initializer(Expression):
    """Initializer list or compound literal"""
    elements: List[tuple[Optional['Designator'], Expression]]


@dataclass
class Designator(ASTNode):
    """Designator for designated initializers"""
    index: Optional[Expression] = None  # For array [index]
    member: Optional[str] = None  # For struct .member


@dataclass
class CompoundLiteral(Expression):
    """Compound literal"""
    type: Type
    initializer: Initializer


# ============== Program Node ==============

@dataclass
class Program(ASTNode):
    """Root node representing entire program"""
    declarations: List[Union[Declaration, FunctionDecl, StructDecl, UnionDecl, TypedefDecl, EnumDecl]]
    external_declarations: List[Statement] = field(default_factory=list)


# ============== Utility Functions ==============

def print_ast(node: ASTNode, indent: int = 0) -> str:
    """Pretty-print AST node"""
    prefix = "  " * indent
    
    if isinstance(node, Program):
        result = f"{prefix}Program\n"
        for decl in node.declarations:
            result += print_ast(decl, indent + 1)
        return result
    
    elif isinstance(node, FunctionDecl):
        result = f"{prefix}FunctionDecl: {node.name}\n"
        result += f"{prefix}  ReturnType: {node.return_type}\n"
        result += f"{prefix}  Parameters:\n"
        for param in node.parameters:
            result += print_ast(param, indent + 2)
        if node.body:
            result += f"{prefix}  Body:\n"
            result += print_ast(node.body, indent + 2)
        return result
    
    elif isinstance(node, Declaration):
        result = f"{prefix}Declaration: {node.name} ({node.type})\n"
        if node.initializer:
            result += f"{prefix}  Initializer:\n"
            result += print_ast(node.initializer, indent + 2)
        return result
    
    elif isinstance(node, CompoundStmt):
        result = f"{prefix}CompoundStmt\n"
        for stmt in node.statements:
            result += print_ast(stmt, indent + 1)
        return result
    
    elif isinstance(node, BinaryOp):
        return f"{prefix}BinaryOp({node.operator})\n"
    
    elif isinstance(node, Identifier):
        return f"{prefix}Identifier({node.name})\n"
    
    elif isinstance(node, IntLiteral):
        return f"{prefix}IntLiteral({node.value})\n"
    
    else:
        return f"{prefix}{node.__class__.__name__}\n"
