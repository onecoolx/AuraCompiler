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
from pycc.preprocessor import Preprocessor, _probe_system_include_paths
from pycc.lexer import Lexer, Token
from pycc.parser import Parser
from pycc.semantics import SemanticAnalyzer
from pycc.ir import IRGenerator
from pycc.optimizer import Optimizer
from pycc.codegen import CodeGenerator
from pycc.gcc_extensions import strip_gcc_extensions


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
    
    def __init__(
        self,
        optimize: bool = True,
        *,
        include_paths: Optional[List[str]] = None,
        defines: Optional[dict] = None,
        use_system_cpp: bool = False,
        wall: bool = False,
        werror: bool = False,
    ):
        self.optimize = optimize
        self.wall = wall
        self.werror = werror

        # Preprocessor options (very small subset).
        self._pp_include_paths = list(include_paths or [])
        self._pp_defines = dict(defines or {})
        self._use_system_cpp = use_system_cpp

        # Toolchain defaults (binutils).
        self.assembler = os.environ.get("PYCC_AS", "as")
        self.linker = os.environ.get("PYCC_LD", "ld")
    
    def compile_file(
        self,
        source_file: str,
        output_file: Optional[str] = None,
        *,
        preprocess_only: bool = False,
    ) -> CompilationResult:
        """Compile a source file.

        If output_file endswith:
        - .s : emit assembly
        - .o : assemble with system toolchain
        - otherwise: link to ELF executable (via gcc)
        """
        try:
            with open(source_file, 'r', encoding='utf-8', errors='replace') as f:
                source_code = f.read()
            # Preprocess before lex/parse.
            if self._use_system_cpp:
                try:
                    source_code = self._preprocess_with_system_cpp(source_file)
                except Exception as e:
                    return CompilationResult(success=False, errors=[f"Preprocess failed: {e}"])
            else:
                # Built-in preprocessor (subset).
                try:
                    pp = Preprocessor(include_paths=self._pp_include_paths)
                    pres = pp.preprocess(source_file, initial_macros=self._pp_defines)
                    if not pres.success:
                        return CompilationResult(success=False, errors=[f"Preprocess failed: {e}" for e in (pres.errors or [])])
                    source_code = pres.text
                except Exception as e:
                    return CompilationResult(success=False, errors=[f"Preprocess failed: {e}"])

            # If requested, emit the preprocessed translation unit to a stable
            # sidecar file. This is useful for debugging without changing the
            # main pipeline. Driver can set PYCC_PREPROCESSED_OUT.
            pp_out = os.environ.get("PYCC_PREPROCESSED_OUT")
            if pp_out:
                try:
                    with open(pp_out, "w", encoding="utf-8") as f:
                        f.write(source_code)
                except OSError as e:
                    return CompilationResult(success=False, errors=[f"Failed to write preprocessed output: {e}"])

            if preprocess_only:
                # For -E style calls, return preprocessed text in `assembly`
                # to match existing tests.
                return CompilationResult(success=True, output_file=None, assembly=source_code)

            return self.compile_code(source_code, output_file, source_path=source_file)
        except IOError as e:
            return CompilationResult(
                success=False,
                errors=[f"Failed to read source file: {e}"]
            )

    def compile_files(self, source_files: List[str], output_file: str) -> CompilationResult:
        """Compile and link multiple translation units.

        Current behavior:
        - Always compiles each input to a temporary `.o` using `compile_file(..., .o)`.
        - Links all objects into an executable at `output_file` using the existing
          binutils-based linker pipeline.
        - Does not support emitting a combined `.s`/`.o` as the final output.
        """

        if not source_files:
            return CompilationResult(success=False, errors=["No input files"])

        ext = os.path.splitext(output_file)[1]
        if ext in {".s", ".o"}:
            return CompilationResult(
                success=False,
                errors=["Multi-input mode only supports linking to an executable output"],
            )

        keep_temps = os.environ.get("PYCC_KEEP_TEMPS") in {"1", "true", "yes"}
        td_ctx = tempfile.TemporaryDirectory(prefix="pycc_mf_") if not keep_temps else None
        td = td_ctx.name if td_ctx is not None else tempfile.mkdtemp(prefix="pycc_mf_")
        try:
            # Pre-link cross-TU validation (C89 subset): reject incompatible
            # external object declarations across translation units.
            # This makes errors deterministic (not dependent on the system linker).

            def _canon_global_obj_type(ty: str) -> str:
                """Canonicalize the type string representation for globals.

                The frontend uses stringly-typed bases (e.g. "signed int").
                For multi-TU compatibility checks we normalize common spellings.
                """
                s = " ".join(str(ty).strip().lower().split())
                # normalize pointer formatting
                s = s.replace(" *", "*").replace("* ", "*")
                # normalize common integer spellings
                if s == "signed":
                    s = "signed int"
                if s == "unsigned":
                    s = "unsigned int"
                if s in {"signed int", "int"}:
                    s = "int"
                if s in {"unsigned int"}:
                    s = "unsigned int"
                if s in {"short", "short int", "signed short", "signed short int"}:
                    s = "short"
                if s in {"unsigned short", "unsigned short int"}:
                    s = "unsigned short"
                if s in {"long", "long int", "signed long", "signed long int"}:
                    s = "long"
                if s in {"unsigned long", "unsigned long int"}:
                    s = "unsigned long"
                if s in {"char", "signed char"}:
                    # In this compiler, plain `char` has a platform-defined
                    # signedness; keep it distinct from `signed char`.
                    # (So do not fold signed char into char.)
                    return s
                return s

            def _parse_function_sig(ty: str) -> Optional[tuple[str, Optional[int], bool]]:
                """Parse a function type string from SemanticAnalyzer.

                Expected formats (subset):
                  - "function int"
                  - "function int(...)"  (variadic)
                The semantic pass currently does not encode parameter types.
                We approximate compatibility using return type base + whether
                it is variadic + parameter count (when available).
                For now, param count is None unless the semantic pass encodes it.
                """
                if not isinstance(ty, str):
                    return None
                s = " ".join(ty.strip().split())
                if not s.startswith("function "):
                    return None
                rest = s[len("function ") :].strip()
                # semantic uses a slightly odd "(... )" spelling; tolerate both.
                is_variadic = rest.endswith("(...)") or rest.endswith("(... )")
                if rest.endswith("(... )"):
                    rest = rest[: -len("(... )")].strip()
                elif rest.endswith("(...)"):
                    rest = rest[: -len("(...)")].strip()
                ret = _canon_global_obj_type(rest)
                return (ret, None, is_variadic)
            sym_types: dict[str, str] = {}
            sym_has_non_extern: dict[str, bool] = {}
            sym_strong_defs: dict[str, int] = {}
            fn_sigs: dict[str, tuple[str, Optional[int], bool]] = {}
            fn_param_types: dict[str, Optional[list[str]]] = {}
            for src in source_files:
                try:
                    with open(src, "r", encoding="utf-8") as f:
                        src_text = f.read()
                    if self._use_system_cpp:
                        src_text = self._preprocess_with_system_cpp(src)
                    else:
                        pp = Preprocessor(include_paths=self._pp_include_paths)
                        pres = pp.preprocess(src, initial_macros=self._pp_defines)
                        if not pres.success:
                            return CompilationResult(success=False, errors=[f"Preprocess failed: {e}" for e in (pres.errors or [])])
                        src_text = pres.text

                    tokens = self.get_tokens(src_text)
                    ast = self.get_ast(tokens)
                    sema_ctx, _ = self.analyze_semantics(ast)
                except Exception as e:
                    # Reuse single-file style message as best-effort.
                    return CompilationResult(success=False, errors=[f"error: multi-tu: {e}"])

                gtypes = getattr(sema_ctx, "global_types", {}) or {}
                gkinds = getattr(sema_ctx, "global_kinds", {}) or {}
                glink = getattr(sema_ctx, "global_linkage", {}) or {}
                fsigs = getattr(sema_ctx, "function_sigs", {}) or {}
                fptys = getattr(sema_ctx, "function_param_types", {}) or {}

                for name, ty in gtypes.items():
                    # Functions: check signature compatibility across TUs (subset).
                    # Prefer explicit function_sigs data (includes param count).
                    if name in fsigs:
                        rt, pc, var = fsigs[name]
                        fn_sig = (_canon_global_obj_type(str(rt)), pc, bool(var))
                    else:
                        fn_sig = _parse_function_sig(str(ty))
                    if fn_sig is not None:
                        prev_sig = fn_sigs.get(name)
                        if prev_sig is None:
                            fn_sigs[name] = fn_sig
                        else:
                            if fn_sig != prev_sig:
                                return CompilationResult(
                                    success=False,
                                    errors=[
                                        f"error: multi-tu: incompatible declarations for function '{name}'"
                                    ],
                                )

                        # Keep per-parameter prototype info for future tightening.
                        cur_ptys = fptys.get(name)
                        prev_ptys = fn_param_types.get(name)
                        # Enforce parameter type compatibility when both TUs
                        # provide a prototype (C89 §6.1.2.6).
                        if cur_ptys is not None and prev_ptys is not None:
                            if len(cur_ptys) == len(prev_ptys):
                                for pi, (ct, pt) in enumerate(zip(cur_ptys, prev_ptys)):
                                    ct_c = _canon_global_obj_type(str(ct))
                                    pt_c = _canon_global_obj_type(str(pt))
                                    if ct_c != pt_c:
                                        return CompilationResult(
                                            success=False,
                                            errors=[
                                                f"error: multi-tu: incompatible parameter {pi+1} type for function '{name}': '{pt_c}' vs '{ct_c}'"
                                            ],
                                        )
                        fn_param_types.setdefault(name, cur_ptys)
                        if cur_ptys is not None and fn_param_types[name] is None:
                            fn_param_types[name] = cur_ptys
                        continue
                    # Skip internal linkage symbols (static) since they are TU-local.
                    if glink.get(name) == "internal":
                        continue

                    kind = gkinds.get(name, "")
                    is_extern_only = kind == "extern_decl"
                    if not is_extern_only:
                        sym_has_non_extern[name] = True
                    if kind == "definition":
                        sym_strong_defs[name] = sym_strong_defs.get(name, 0) + 1

                    prev = sym_types.get(name)
                    if prev is None:
                        sym_types[name] = _canon_global_obj_type(str(ty))
                    else:
                        cty = _canon_global_obj_type(str(ty))
                        if cty != prev:
                            return CompilationResult(
                                success=False,
                                errors=[f"error: multi-tu: incompatible types for global '{name}': '{prev}' vs '{cty}'"],
                            )
            # If a name was only ever seen as `extern` declarations, it doesn't
            # participate in compatibility checks here (no definition in the set).
            # This matters for deterministic behavior when headers declare symbols
            # not provided by the current link set.
            sym_types = {k: v for k, v in sym_types.items() if sym_has_non_extern.get(k)}

            # Deterministic error for multiple strong external definitions.
            for name, n in sym_strong_defs.items():
                if n > 1:
                    return CompilationResult(
                        success=False,
                        errors=[f"error: multi-tu: multiple external definitions of global '{name}'"],
                    )

            obj_paths: List[str] = []
            for i, src in enumerate(source_files):
                obj_path = os.path.join(td, f"tu{i}.o")
                res = self.compile_file(src, obj_path)
                if not res.success:
                    return CompilationResult(success=False, errors=list(res.errors or []), warnings=list(res.warnings or []))
                obj_paths.append(obj_path)

            # Link all objects into the final executable.
            # We reuse the same default link strategy as single-file mode.
            cmd: List[str] = [self.linker, "-o", output_file]
            cmd.extend(obj_paths)
            # Add libc/crt/etc.
            # Use a dummy object path just to compute the full cmd, then swap.
            # (This keeps link behavior identical to the single-TU path.)
            link_cmd = self._default_link_cmd(o_path=obj_paths[0], out_path=output_file)
            # link_cmd structure: [ld, -o, out, ...crt..., o_path, ...libs...]
            # Replace the single o_path occurrence with all obj_paths.
            try:
                o_idx = link_cmd.index(obj_paths[0])
            except ValueError:
                # Fallback: just append objects.
                final_cmd = link_cmd + obj_paths[1:]
            else:
                final_cmd = link_cmd[:o_idx] + obj_paths + link_cmd[o_idx + 1 :]

            self._run(final_cmd, "link")

            return CompilationResult(success=True, output_file=output_file)
        except (IOError, subprocess.CalledProcessError) as e:
            if isinstance(e, subprocess.CalledProcessError):
                detail = getattr(e, "stderr", None) or getattr(e, "output", None)
                if detail:
                    return CompilationResult(success=False, errors=[f"Linking failed: {e}\n{detail}"])
            return CompilationResult(success=False, errors=[f"Linking failed: {e}"])
        finally:
            if td_ctx is not None:
                td_ctx.cleanup()

    def _preprocess_with_system_cpp(self, source_file: str) -> str:
        gcc = shutil.which("gcc")
        if not gcc:
            raise RuntimeError("gcc not found")
        # Use gnu89 mode: glibc headers rely on GNU extensions and builtin tokens.
        cmd: List[str] = [
            gcc,
            "-std=gnu89",
            "-E",
            "-P",
            # Let gcc use its default system include search. We only add user
            # include paths (-I) below.
            "-nostdinc",
            # Re-add gcc's default system include dirs explicitly so behavior is
            # stable even when we customize include paths.
            # NOTE: we intentionally *do not* set -nostdinc++.
        ]

        # Prefer gcc's own default include dirs. This avoids depending on our
        # built-in preprocessor's best-effort system probing.
        # We compute these by running: gcc -E -Wp,-v -
        sys_includes = _probe_system_include_paths()
        for inc in sys_includes:
            cmd += ["-isystem", inc]

        # Reduce the complexity of glibc headers for our subset compiler.
        # These avoid typedefs and builtins that we don't parse yet.
        cmd += [
            "-D__GNUG__=0",
            "-D__GNUC_PREREQ(maj,min)=0",
            "-D__glibc_clang_has_extension(x)=0",
            "-D__has_extension(x)=0",
            "-D__has_feature(x)=0",
            "-D__has_builtin(x)=0",
            "-D__has_attribute(x)=0",
            "-D__has_declspec_attribute(x)=0",
            "-D__has_cpp_attribute(x)=0",
            "-D__builtin_va_list=void *",
            # Remaining macros not handled by strip_gcc_extensions().
            "-Drestrict=",
            "-D__forceinline=",
            # GCC builtin functions used in system headers
            "-D__builtin_bswap16(x)=(x)",
            "-D__builtin_bswap32(x)=(x)",
            "-D__builtin_bswap64(x)=(x)",
            "-D__builtin_expect(x,y)=(x)",
            "-D__builtin_constant_p(x)=0",
            "-D__builtin_types_compatible_p(x,y)=0",
            "-D__builtin_offsetof(t,m)=((unsigned long)&((t*)0)->m)",
            # GCC typeof (used in some system macros)
            "-D__typeof__(x)=int",
            "-D__typeof(x)=int",
            # Misc GCC extensions
            "-D__THROW=",
            "-D__nonnull(x)=",
            "-D__wur=",
            "-DNDEBUG",
            "-D__null=0",
        ]
        for d in self._pp_include_paths:
            cmd += ["-I", d]
        for k, v in self._pp_defines.items():
            cmd += [f"-D{k}={v}"]
        cmd += [source_file]
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if p.returncode != 0:
            msg = p.stderr.strip() or p.stdout.strip() or "(no output)"
            raise RuntimeError(f"system cpp failed: {msg}")
        # Post-process: strip GCC extensions that survived macro expansion.
        return strip_gcc_extensions(p.stdout)
    
    def compile_code(self, source_code: str, output_file: Optional[str] = None, source_path: str = "<input>") -> CompilationResult:
        """Compile source code"""
        errors = []
        warnings = []
        assembly = None

        def _fmt_error(*, phase: str, msg: str) -> str:
            """Format an error in a consistent, testable way.

            Format:
              error: <phase>: <message> (at <file>:<line>:<col>)
            Location is best-effort.
            """

            loc = None

            # ParserError already includes `... at L:C` in its str().
            if " at " in msg:
                left, right = msg.rsplit(" at ", 1)
                if ":" in right:
                    loc = right.strip()
                    msg = left.strip()

            if loc is None:
                loc = "?:?:?"

            return f"error: {phase}: {msg} (at {source_path}:{loc})"
        
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
            return CompilationResult(success=False, errors=[_fmt_error(phase="syntax", msg=str(e))])
        
        # Phase 3: Semantic Analysis
        try:
            sema_ctx, analyzer = self.analyze_semantics(ast)
            warnings.extend(list(getattr(analyzer, "warnings", []) or []))
        except Exception as e:
            return CompilationResult(success=False, errors=[_fmt_error(phase="semantics", msg=str(e))], warnings=warnings)

        # -Werror: treat warnings as errors
        if getattr(self, "werror", False) and warnings:
            return CompilationResult(
                success=False,
                errors=[f"error (via -Werror): {w}" for w in warnings],
                warnings=warnings,
            )
        
        # Phase 4: IR Generation
        try:
            ir = self.get_ir(ast, sema_ctx=sema_ctx)
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

                # Optionally keep a copy of the generated assembly (sidecar).
                asm_out = os.environ.get("PYCC_ASSEMBLY_OUT")
                if asm_out and asm_out != out:
                    try:
                        with open(asm_out, "w", encoding="utf-8") as f:
                            f.write(assembly)
                    except OSError as e:
                        return CompilationResult(success=False, errors=[f"Failed to write assembly output: {e}"])

            elif ext == ".o":
                with tempfile.TemporaryDirectory() as td:
                    s_path = os.path.join(td, "out.s")
                    try:
                        with open(s_path, 'w') as f:
                            f.write(assembly)
                        self._run([self.assembler, "-o", out, s_path], "assemble")
                    except (IOError, subprocess.CalledProcessError) as e:
                        return CompilationResult(success=False, errors=[f"Assembling failed: {e}"])

                # Optionally keep a copy of the generated assembly and/or object.
                asm_out = os.environ.get("PYCC_ASSEMBLY_OUT")
                if asm_out:
                    try:
                        with open(asm_out, "w", encoding="utf-8") as f:
                            f.write(assembly)
                    except OSError as e:
                        return CompilationResult(success=False, errors=[f"Failed to write assembly output: {e}"])
                obj_out = os.environ.get("PYCC_OBJECT_OUT")
                if obj_out and obj_out != out:
                    try:
                        shutil.copyfile(out, obj_out)
                    except OSError as e:
                        return CompilationResult(success=False, errors=[f"Failed to write object output: {e}"])

            else:
                # link to ELF using binutils (as + ld) and a C runtime (glibc dev preferred; fallback newlib)
                # Keep temp files if requested to simplify debugging.
                keep_temps = os.environ.get("PYCC_KEEP_TEMPS") in {"1", "true", "yes"}
                td_ctx = tempfile.TemporaryDirectory() if not keep_temps else None
                td = td_ctx.name if td_ctx is not None else tempfile.mkdtemp(prefix="pycc-")
                try:
                    s_path = os.path.join(td, "out.s")
                    o_path = os.path.join(td, "out.o")
                    try:
                        with open(s_path, 'w') as f:
                            f.write(assembly)

                        # Optionally keep a copy of the generated assembly.
                        asm_out = os.environ.get("PYCC_ASSEMBLY_OUT")
                        if asm_out:
                            try:
                                with open(asm_out, "w", encoding="utf-8") as f2:
                                    f2.write(assembly)
                            except OSError as e:
                                return CompilationResult(success=False, errors=[f"Failed to write assembly output: {e}"])

                        self._run([self.assembler, "-o", o_path, s_path], "assemble")

                        # Optionally keep a copy of the generated object.
                        obj_out = os.environ.get("PYCC_OBJECT_OUT")
                        if obj_out:
                            try:
                                shutil.copyfile(o_path, obj_out)
                            except OSError as e:
                                return CompilationResult(success=False, errors=[f"Failed to write object output: {e}"])

                        link_cmd = self._default_link_cmd(o_path=o_path, out_path=out)
                        self._run(link_cmd, "link")
                    except (IOError, subprocess.CalledProcessError) as e:
                        if isinstance(e, subprocess.CalledProcessError):
                            detail = getattr(e, "stderr", None) or getattr(e, "output", None)
                            if detail:
                                return CompilationResult(
                                    success=False,
                                    errors=[f"Linking failed: {e}\n{detail}"],
                                )
                        return CompilationResult(success=False, errors=[f"Linking failed: {e}"])
                finally:
                    if td_ctx is not None:
                        td_ctx.cleanup()
        
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
            raise RuntimeError("\n".join(str(e) for e in errors))
        return tokens
    
    def get_ast(self, tokens: List[Token]):
        """Get AST from tokens"""
        parser = Parser(tokens)
        return parser.parse()
    
    def analyze_semantics(self, ast):
        """Perform semantic analysis"""
        analyzer = SemanticAnalyzer(wall=getattr(self, "wall", False))
        sema_ctx = analyzer.analyze(ast)
        return sema_ctx, analyzer
    
    def get_ir(self, ast, sema_ctx=None):
        """Generate IR from AST"""
        generator = IRGenerator()
        # Optional semantic context enables better lowering decisions
        # (e.g. signed/unsigned comparisons).
        if sema_ctx is not None:
            setattr(generator, "_sema_ctx", sema_ctx)
        return generator.generate(ast)
    
    def optimize_ir(self, ir):
        """Optimize IR"""
        optimizer = Optimizer()
        return optimizer.optimize(ir)
    
    def get_assembly(self, ir, sema_ctx=None):
        """Generate assembly from IR"""
        generator = CodeGenerator(self.optimize, sema_ctx=sema_ctx)
        asm = generator.generate(ir)
        return asm


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(prog="pycc", description="AuraCompiler")
    ap.add_argument("source", help="Input C file")
    ap.add_argument("-o", dest="output", required=True, help="Output: .s, .o, or executable path")
    ap.add_argument("--no-opt", action="store_true", help="Disable optimizations")

    args = ap.parse_args()

    compiler = Compiler(optimize=not args.no_opt)
    result = compiler.compile_file(args.source, args.output)
    if result.success:
        pass
    else:
        pass
    raise SystemExit(0 if result.success else 1)
