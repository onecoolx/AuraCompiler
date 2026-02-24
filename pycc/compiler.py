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
import shutil
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

        # Toolchain defaults (binutils).
        self.assembler = os.environ.get("PYCC_AS", "as")
        self.linker = os.environ.get("PYCC_LD", "ld")
    
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
            sema_ctx = self.analyze_semantics(ast)
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
            assembly = self.get_assembly(ir, sema_ctx=sema_ctx)
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
                        self._run([self.assembler, "-o", out, s_path], "assemble")
                    except (IOError, subprocess.CalledProcessError) as e:
                        return CompilationResult(success=False, errors=[f"Assembling failed: {e}"])

            else:
                # link to ELF using binutils (as + ld) and a C runtime (glibc dev preferred; fallback newlib)
                with tempfile.TemporaryDirectory() as td:
                    s_path = os.path.join(td, "out.s")
                    o_path = os.path.join(td, "out.o")
                    try:
                        with open(s_path, 'w') as f:
                            f.write(assembly)
                        self._run([self.assembler, "-o", o_path, s_path], "assemble")
                        link_cmd = self._default_link_cmd(o_path=o_path, out_path=out)
                        self._run(link_cmd, "link")
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
        p = subprocess.run(cmd, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if p.returncode != 0:
            msg = p.stderr.strip() or p.stdout.strip() or "(no output)"
            raise subprocess.CalledProcessError(p.returncode, cmd, output=p.stdout, stderr=msg)

    def _default_link_cmd(self, o_path: str, out_path: str) -> List[str]:
        """Return a default `ld` command.

        Strategy:
        - Prefer glibc dev setup using `ld --dynamic-linker ...` and `-lc`.
        - If glibc dev files aren't present, try a best-effort newlib layout.
        - If neither looks usable, raise a helpful error.
        """
        as_path = shutil.which("as")
        ld_path = shutil.which(self.linker)
        if not as_path or not ld_path:
            raise RuntimeError("binutils not found: please install 'as' and 'ld'")

        # Detect platform dynamic linker (glibc)
        dyn_linker_candidates = [
            "/lib64/ld-linux-x86-64.so.2",
            "/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2",
            "/lib/ld-linux-x86-64.so.2",
        ]
        dyn_linker = next((p for p in dyn_linker_candidates if os.path.exists(p)), None)

        # Common glibc CRT objects
        crt1_candidates = [
            "/usr/lib/x86_64-linux-gnu/crt1.o",
            "/usr/lib64/crt1.o",
            "/usr/lib/crt1.o",
        ]
        crti_candidates = [
            "/usr/lib/x86_64-linux-gnu/crti.o",
            "/usr/lib64/crti.o",
            "/usr/lib/crti.o",
        ]
        crtn_candidates = [
            "/usr/lib/x86_64-linux-gnu/crtn.o",
            "/usr/lib64/crtn.o",
            "/usr/lib/crtn.o",
        ]
        crtbegin_candidates = [
            "/usr/lib/gcc/x86_64-linux-gnu",  # prefix only; probed below
            "/usr/lib/gcc/x86_64-pc-linux-gnu",
            "/usr/lib/gcc/x86_64-linux-gnu",
        ]

        def _first_existing(paths: List[str]) -> Optional[str]:
            return next((p for p in paths if os.path.exists(p)), None)

        crt1 = _first_existing(crt1_candidates)
        crti = _first_existing(crti_candidates)
        crtn = _first_existing(crtn_candidates)

        # Probe for crtbegin/crtend under gcc libdir if present.
        crtbegin = None
        crtend = None
        for prefix in crtbegin_candidates:
            if not os.path.isdir(prefix):
                continue
            # choose highest version directory
            try:
                vers = sorted([d for d in os.listdir(prefix) if os.path.isdir(os.path.join(prefix, d))])
            except Exception:
                continue
            for v in reversed(vers):
                cb = os.path.join(prefix, v, "crtbegin.o")
                ce = os.path.join(prefix, v, "crtend.o")
                if os.path.exists(cb) and os.path.exists(ce):
                    crtbegin = cb
                    crtend = ce
                    break
            if crtbegin and crtend:
                break

        # If glibc dev bits look present, link like a normal ELF executable.
        if dyn_linker and crt1 and crti and crtn and crtbegin and crtend:
            # Library search dirs (best-effort)
            libdirs = [
                "/lib/x86_64-linux-gnu",
                "/usr/lib/x86_64-linux-gnu",
                "/lib64",
                "/usr/lib64",
                "/lib",
                "/usr/lib",
            ]
            # Also include GCC runtime library dirs so `-lgcc`/`-lgcc_s` can resolve.
            gcc_libdirs: List[str] = []
            for prefix in [
                "/usr/lib/gcc/x86_64-linux-gnu",
                "/usr/lib/gcc/x86_64-pc-linux-gnu",
                "/usr/lib/gcc/x86_64-linux-gnu",
            ]:
                if not os.path.isdir(prefix):
                    continue
                try:
                    vers = sorted([d for d in os.listdir(prefix) if os.path.isdir(os.path.join(prefix, d))])
                except Exception:
                    continue
                for v in reversed(vers):
                    d = os.path.join(prefix, v)
                    if os.path.isdir(d):
                        gcc_libdirs.append(d)
                        break
            libdirs = gcc_libdirs + libdirs

            cmd: List[str] = [
                self.linker,
                "-o",
                out_path,
                "-dynamic-linker",
                dyn_linker,
                crt1,
                crti,
                crtbegin,
                o_path,
            ]
            for d in libdirs:
                if os.path.isdir(d):
                    cmd += ["-L", d]
            cmd += ["-lc", "-lgcc", "-lgcc_s", crtend, crtn]
            return cmd

        # Fallback: try newlib-ish layout (static) if present.
        # Note: this is best-effort; newlib is commonly used with cross toolchains.
        newlib_candidates = [
            "/usr/lib/libc.a",
            "/usr/lib64/libc.a",
            "/usr/x86_64-unknown-elf/lib/libc.a",
            "/usr/local/x86_64-unknown-elf/lib/libc.a",
        ]
        libc_a = _first_existing(newlib_candidates)
        if libc_a:
            libdir = os.path.dirname(libc_a)
            cmd = [self.linker, "-o", out_path, o_path, "-L", libdir, "-lc"]
            return cmd

        raise RuntimeError(
            "No usable C runtime found for linking. Install a C development runtime (glibc-dev / libc6-dev), "
            "or install a newlib toolchain."
        )
    
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
        return analyzer.analyze(ast)
    
    def get_ir(self, ast):
        """Generate IR from AST"""
        generator = IRGenerator()
        return generator.generate(ast)
    
    def optimize_ir(self, ir):
        """Optimize IR"""
        optimizer = Optimizer()
        return optimizer.optimize(ir)
    
    def get_assembly(self, ir, sema_ctx=None):
        """Generate assembly from IR"""
        generator = CodeGenerator(self.optimize, sema_ctx=sema_ctx)
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
