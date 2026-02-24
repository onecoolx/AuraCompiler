"""
Main Compiler Driver

Orchestrates the compilation pipeline.
"""

from __future__ import annotations

from typing import Optional, List
from dataclasses import dataclass
import os
import subprocess
import tempfile
from pycc.lexer import Lexer, Token
from pycc.parser import Parser
from pycc.semantics import SemanticAnalyzer
from pycc.ir import IRGenerator
from pycc.optimizer import Optimizer
from pycc.codegen import CodeGenerator


@dataclass
class CompilationResult:
    """Result of compilation"""
    success: bool
    output_file: Optional[str] = None
    errors: List[str] = None
    warnings: List[str] = None
    assembly: Optional[str] = None
    
    def __post_init__(self):
        if self.errors is None:
            self.errors = []
        if self.warnings is None:
            self.warnings = []


class Compiler:
    """Main compiler class orchestrating all compilation stages"""
    
    def __init__(self, optimize: bool = True):
        self.optimize = optimize
    
    def compile_file(self, source_file: str, output_file: Optional[str] = None) -> CompilationResult:
        """Compile a source file.

        If output_file endswith:
        - .s : emit assembly
        - .o : assemble with system toolchain
        - otherwise: link to ELF executable (via gcc)
        """
        try:
            with open(source_file, 'r') as f:
                source_code = f.read()
            return self.compile_code(source_code, output_file, source_path=source_file)
        except IOError as e:
            return CompilationResult(
                success=False,
                errors=[f"Failed to read source file: {e}"]
            )
    
    def compile_code(self, source_code: str, output_file: Optional[str] = None, source_path: str = "<input>") -> CompilationResult:
        """Compile source code"""
        errors = []
        warnings = []
        assembly = None
        
        # Phase 1: Lexical Analysis
        try:
            tokens = self.get_tokens(source_code)
            if not tokens:
                return CompilationResult(success=False, errors=["No tokens generated"])
        except Exception as e:
            return CompilationResult(success=False, errors=[f"Lexical analysis failed: {e}"])
        
        # Phase 2: Syntax Analysis
        try:
            ast = self.get_ast(tokens)
        except Exception as e:
            return CompilationResult(success=False, errors=[f"Syntax analysis failed: {e}"])
        
        # Phase 3: Semantic Analysis
        try:
            self.analyze_semantics(ast)
        except Exception as e:
            return CompilationResult(success=False, errors=[f"Semantic analysis failed: {e}"])
        
        # Phase 4: IR Generation
        try:
            ir = self.get_ir(ast)
        except Exception as e:
            return CompilationResult(success=False, errors=[f"IR generation failed: {e}"])
        
        # Phase 5: Optimization
        if self.optimize:
            try:
                ir = self.optimize_ir(ir)
            except Exception as e:
                warnings.append(f"Optimization failed: {e}")
        
        # Phase 6: Code Generation
        try:
            assembly = self.get_assembly(ir)
        except Exception as e:
            return CompilationResult(success=False, errors=[f"Code generation failed: {e}"])
        
        # Write output / assemble / link
        if output_file:
            out = output_file
            ext = os.path.splitext(out)[1]

            if ext == ".s":
                try:
                    with open(out, 'w') as f:
                        f.write(assembly)
                except IOError as e:
                    return CompilationResult(success=False, errors=[f"Failed to write output file: {e}"])

            elif ext == ".o":
                with tempfile.TemporaryDirectory() as td:
                    s_path = os.path.join(td, "out.s")
                    try:
                        with open(s_path, 'w') as f:
                            f.write(assembly)
                        self._run(["as", "-o", out, s_path], "assemble")
                    except (IOError, subprocess.CalledProcessError) as e:
                        return CompilationResult(success=False, errors=[f"Assembling failed: {e}"])

            else:
                # link to ELF using gcc (glibc/newlib toolchain as configured on system)
                with tempfile.TemporaryDirectory() as td:
                    s_path = os.path.join(td, "out.s")
                    o_path = os.path.join(td, "out.o")
                    try:
                        with open(s_path, 'w') as f:
                            f.write(assembly)
                        self._run(["as", "-o", o_path, s_path], "assemble")
                        self._run(["gcc", "-o", out, o_path], "link")
                    except (IOError, subprocess.CalledProcessError) as e:
                        return CompilationResult(success=False, errors=[f"Linking failed: {e}"])
        
        return CompilationResult(
            success=True,
            output_file=output_file,
            assembly=assembly,
            errors=errors,
            warnings=warnings
        )

    def _run(self, cmd: List[str], what: str) -> None:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    
    def get_tokens(self, source_code: str) -> List[Token]:
        """Get tokens from source code"""
        lexer = Lexer(source_code)
        tokens = lexer.tokenize()
        if lexer.has_errors():
            errors = lexer.get_errors()
            raise Exception("\n".join(str(e) for e in errors))
        return tokens
    
    def get_ast(self, tokens: List[Token]):
        """Get AST from tokens"""
        parser = Parser(tokens)
        return parser.parse()
    
    def analyze_semantics(self, ast):
        """Perform semantic analysis"""
        analyzer = SemanticAnalyzer()
        analyzer.analyze(ast)
    
    def get_ir(self, ast):
        """Generate IR from AST"""
        generator = IRGenerator()
        return generator.generate(ast)
    
    def optimize_ir(self, ir):
        """Optimize IR"""
        optimizer = Optimizer()
        return optimizer.optimize(ir)
    
    def get_assembly(self, ir):
        """Generate assembly from IR"""
        generator = CodeGenerator(self.optimize)
        return generator.generate(ir)


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(prog="pycc", description="AuraCompiler (MVP)")
    ap.add_argument("source", help="Input C file")
    ap.add_argument("-o", dest="output", required=True, help="Output: .s, .o, or executable path")
    ap.add_argument("--no-opt", action="store_true", help="Disable optimizations")

    args = ap.parse_args()

    compiler = Compiler(optimize=not args.no_opt)
    result = compiler.compile_file(args.source, args.output)
    if result.success:
        print("Compilation successful!")
        print(f"Output: {args.output}")
    else:
        print("Compilation failed:")
        for e in result.errors:
            print(f"  Error: {e}")
    raise SystemExit(0 if result.success else 1)
