"""
PyCC - Pure Python C99 Compiler

A complete implementation of a C99 compiler written in pure Python,
following the classic three-stage compiler architecture.
"""

__version__ = "0.1.0"
__author__ = "PyCC Contributors"
__license__ = "MIT"

from .lexer import Lexer, Token
from .parser import Parser
from .semantics import SemanticAnalyzer
from .ir import IRGenerator
from .optimizer import Optimizer
from .codegen import CodeGenerator
from .compiler import Compiler

__all__ = [
    'Lexer',
    'Token',
    'Parser',
    'SemanticAnalyzer',
    'IRGenerator',
    'Optimizer',
    'CodeGenerator',
    'Compiler',
]
