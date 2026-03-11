#!/usr/bin/env python3
"""pycc - top-level CLI wrapper for AuraCompiler

Compatible with Python 3.8+.

Usage examples:
  ./pycc.py examples/hello.c -o hello
  ./pycc.py input.c -o out.s
"""
from __future__ import annotations

import argparse
import sys
from typing import Dict, List, Optional

import os
import tempfile
import subprocess

from pycc.preprocessor import Preprocessor

from pycc.compiler import Compiler


def main(argv: Optional[List[str]] = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    # argparse supports `--` end-of-options by default. However, this driver also
    # uses the gcc convention that a lone `-` *as the input file* means "read from
    # stdin". To allow compiling a literal file named `-`, accept `-- -` and treat
    # it as a filename.
    stdin_dash_allowed = True
    if len(argv) >= 2 and argv[0] == "--" and argv[1] == "-":
        stdin_dash_allowed = False

    ap = argparse.ArgumentParser(prog="pycc", description="AuraCompiler CLI")
    ap.add_argument("source", nargs="*", help="Input C source file(s)")
    ap.add_argument("-E", action="store_true", help="Preprocess only (subset: passthrough)")
    ap.add_argument("-S", action="store_true", help="Compile only; emit assembly (.s)")
    ap.add_argument("-c", action="store_true", help="Compile only; emit object (.o)")
    ap.add_argument(
        "--use-system-cpp",
        action="store_true",
        help="Preprocess with system gcc -E before compiling (subset; for glibc headers)",
    )
    ap.add_argument(
        "-D",
        dest="defines",
        action="append",
        default=[],
        metavar="NAME[=VALUE]",
        help="Define a macro for preprocessing (subset)",
    )
    ap.add_argument(
        "-U",
        dest="undefines",
        action="append",
        default=[],
        metavar="NAME",
        help="Undefine a macro for preprocessing (subset)",
    )
    ap.add_argument(
        "-I",
        dest="include_dirs",
        action="append",
        default=[],
        metavar="DIR",
        help="Add an include directory for preprocessing (subset)",
    )
    ap.add_argument(
        "-v",
        dest="verbose",
        action="store_true",
        help="Verbose driver output (print invoked toolchain commands)",
    )
    ap.add_argument(
        "--version",
        action="store_true",
        help="Print version information and exit",
    )
    ap.add_argument(
        "--print-asm",
        action="store_true",
        help="Print generated assembly to stdout (single input only; implies -S)",
    )
    ap.add_argument(
        "--save-temps",
        action="store_true",
        help="Keep intermediate files (.i/.s/.o) when possible",
    )
    ap.add_argument(
        "--dump-preprocessed-to",
        dest="dump_preprocessed_to",
        metavar="PATH",
        help="Write preprocessed output to PATH (single input only; debug)",
    )
    ap.add_argument(
        "--dump-preprocessed-only-to",
        dest="dump_preprocessed_only_to",
        metavar="PATH",
        help="Write preprocessed output to PATH and stop (single input only)",
    )
    ap.add_argument(
        "--dump-preprocessed",
        action="store_true",
        help="Write preprocessed output to pycc-tmp.i (single input only)",
    )
    ap.add_argument(
        "--dump-ir",
        action="store_true",
        help="Write IR to pycc-tmp.ir (single input only; debug)",
    )
    ap.add_argument(
        "--dump-ir-to",
        dest="dump_ir_to",
        metavar="PATH",
        help="Write IR to PATH (single input only; debug)",
    )
    ap.add_argument(
        "--dump-ir-only-to",
        dest="dump_ir_only_to",
        metavar="PATH",
        help="Write IR to PATH and stop (single input only)",
    )
    ap.add_argument(
        "--dump-asm",
        action="store_true",
        help="Write assembly to pycc-tmp.s (single input only; debug)",
    )
    ap.add_argument(
        "--dump-asm-to",
        dest="dump_asm_to",
        metavar="PATH",
        help="Write assembly to PATH (single input only; debug)",
    )
    ap.add_argument(
        "--dump-asm-only-to",
        dest="dump_asm_only_to",
        metavar="PATH",
        help="Write assembly to PATH and stop (single input only)",
    )
    ap.add_argument(
        "--dump-tokens",
        action="store_true",
        help="Write lexer tokens to pycc-tmp.tokens (single input only; debug)",
    )
    ap.add_argument(
        "--dump-tokens-to",
        dest="dump_tokens_to",
        metavar="PATH",
        help="Write lexer tokens to PATH (single input only; debug)",
    )
    ap.add_argument(
        "--dump-tokens-only-to",
        dest="dump_tokens_only_to",
        metavar="PATH",
        help="Write lexer tokens to PATH and stop (single input only)",
    )
    ap.add_argument("-o", dest="output", required=False, help="Output: .s, .o, or executable")
    ap.add_argument("--no-opt", action="store_true", help="Disable optimizations")
    args = ap.parse_args(argv)

    if args.version:
        # Keep this intentionally simple and stable for tests/scripts.
        print("pycc (AuraCompiler)")
        return 0

    if not args.source:
        print("Error: missing input file")
        return 1

    # Support a gcc-like --save-temps for the main compilation pipeline.
    # We implement this by asking Compiler to write sidecar outputs.
    # (Debug dump flags remain separate and can be used independently.)
    if args.save_temps:
        # Policy B: avoid redundant sidecars.
        # - always keep preprocessed (.i)
        # - keep assembly (.s) unless the main output is already .s
        # - keep object (.o) only for link-to-exe outputs (not when main output is .o)
        os.environ.setdefault("PYCC_PREPROCESSED_OUT", "pycc-tmp.i")
        if not args.S:
            os.environ.setdefault("PYCC_ASSEMBLY_OUT", "pycc-tmp.s")
        if (not args.c) and (not args.S):
            os.environ.setdefault("PYCC_OBJECT_OUT", "pycc-tmp.o")

    # --dump-preprocessed is handled later, after compile_defines is built.

    if args.print_asm:
        # Convenience mode for debugging; does not change Compiler internals.
        # Only support one input for now.
        if len(args.source) != 1:
            print("Error: --print-asm currently supports exactly one input file")
            return 1
        # If user also passed -c, reject.
        if args.c:
            print("Error: --print-asm cannot be combined with -c")
            return 1
        # Force assembly output via a temporary file.
        args.S = True

    if args.S and args.c:
        print("Error: -S and -c are mutually exclusive")
        return 1

    # Preprocessor stage (subset): passthrough the first input.
    if args.E:
        # For now, only support a single input in -E mode.
        if len(args.source) != 1:
            print("Error: -E currently supports exactly one input file")
            return 1

        # gcc-style: '-' means read source from stdin.
        # But allow `-- -` to refer to a literal file named '-'.
        if stdin_dash_allowed and args.source[0] == "-":
            try:
                src_text = sys.stdin.read()
            except Exception as e:
                print(f"Error: cannot read stdin: {e}")
                return 1
            fd, tmp_c = tempfile.mkstemp(prefix="pycc_stdin_", suffix=".c")
            os.close(fd)
            try:
                with open(tmp_c, "w", encoding="utf-8") as f:
                    f.write(src_text)
                args.source[0] = tmp_c
                src_is_temp = True
            except OSError as e:
                print(f"Error: cannot write temp source: {e}")
                try:
                    os.unlink(tmp_c)
                except OSError:
                    pass
                return 1
        else:
            src_is_temp = False

        initial_macros: Dict[str, str] = {}
        for item in args.defines:
            if not item:
                continue
            if "=" in item:
                name, val = item.split("=", 1)
                name = name.strip()
                val = val.strip()
            else:
                name, val = item.strip(), "1"
            if not name:
                print(f"Error: invalid -D argument: {item!r}")
                return 1
            initial_macros[name] = val

        for name in args.undefines:
            if name is None:
                continue
            name = name.strip()
            if not name:
                print("Error: invalid -U argument")
                return 1
            initial_macros.pop(name, None)

        src = args.source[0]
        try:
            if args.use_system_cpp:
                # Reuse the compiler's system-cpp preprocessing path so -E
                # behaves consistently with normal compilation.
                c = Compiler(
                    optimize=False,
                    include_paths=args.include_dirs,
                    defines=initial_macros,
                    use_system_cpp=True,
                )
                text = c._preprocess_with_system_cpp(src)
            else:
                pp = Preprocessor(include_paths=args.include_dirs)
                res = pp.preprocess(src, initial_macros=initial_macros)
                if not res.success:
                    for e in (res.errors or []):
                        print(f"Error: {e}")
                    return 1
                text = res.text
        except Exception as e:
            print(f"Error: {e}")
            if src_is_temp:
                try:
                    os.unlink(src)
                except OSError:
                    pass
            return 1
        if args.output:
            try:
                open(args.output, "w", encoding="utf-8").write(text)
            except OSError as e:
                print(f"Error: cannot write {args.output}: {e}")
                if src_is_temp:
                    try:
                        os.unlink(src)
                    except OSError:
                        pass
                return 1
        else:
            sys.stdout.write(text)

        if src_is_temp:
            try:
                os.unlink(src)
            except OSError:
                pass
        return 0

    # NOTE: -D/-U/-I are accepted for compilation as well; they are wired into
    # Compiler(define/include_paths) below. The help text previously said
    # "-E only"; that is outdated and should be updated in a follow-up.

    # If --print-asm, we may override output path to a temporary .s file.
    temp_asm_path: Optional[str] = None

    if not args.output:
        # gcc/clang default:
        # - no -o, single input, not -c/-S -> a.out
        # - no -o, single input, -S -> source basename .s
        # - no -o, single input, -c -> source basename .o
        if len(args.source) != 1:
            print("Error: -o is required for multi-input mode")
            return 1
        src0 = args.source[0]
        base, _ext = os.path.splitext(os.path.basename(src0))
        if args.S:
            args.output = base + ".s"
        elif args.c:
            args.output = base + ".o"
        else:
            args.output = "a.out"

    # If --print-asm is set, always compile to a temp `.s`.
    if args.print_asm:
        if args.save_temps:
            # Save in current working directory using a stable name.
            args.output = "pycc-tmp.s"
        else:
            fd, temp = tempfile.mkstemp(prefix="pycc_", suffix=".s")
            os.close(fd)
            temp_asm_path = temp
            args.output = temp_asm_path

    # If -S/-c were requested, ensure the output extension matches.
    if args.S and not str(args.output).endswith(".s"):
        print("Error: -S requires -o <file.s> (or omit -o to use <source>.s)")
        return 1
    if args.c and not str(args.output).endswith(".o"):
        print("Error: -c requires -o <file.o> (or omit -o to use <source>.o)")
        return 1

    compile_defines: Dict[str, str] = {}
    for item in args.defines:
        if not item:
            continue
        if "=" in item:
            name, val = item.split("=", 1)
            name = name.strip()
            val = val.strip()
        else:
            name, val = item.strip(), "1"
        if not name:
            print(f"Error: invalid -D argument: {item!r}")
            return 1
        compile_defines[name] = val
    for name in args.undefines:
        if name is None:
            continue
        name = name.strip()
        if not name:
            print("Error: invalid -U argument")
            return 1
        compile_defines.pop(name, None)

    if args.dump_tokens_only_to:
        if len(args.source) != 1:
            print("Error: --dump-tokens-only-to currently supports exactly one input file")
            return 1
        try:
            src = args.source[0]
            cc = Compiler(
                optimize=False,
                include_paths=args.include_dirs,
                defines=compile_defines,
                use_system_cpp=args.use_system_cpp,
            )
            pres = cc.compile_file(src, None, preprocess_only=True)
            if not pres.success:
                for e in pres.errors:
                    print("Error:", e)
                return 1
            toks = cc.get_tokens(pres.assembly or "")
            with open(args.dump_tokens_only_to, "w", encoding="utf-8") as f:
                for t in toks:
                    f.write(str(t) + "\n")
            if args.verbose:
                print(f"[pycc] tokens: {src} -> {args.dump_tokens_only_to}")
            return 0
        except Exception as e:
            print(f"Error: {e}")
            return 1

    if args.dump_tokens or args.dump_tokens_to:
        if len(args.source) != 1:
            print("Error: --dump-tokens currently supports exactly one input file")
            return 1
        try:
            src = args.source[0]
            cc = Compiler(
                optimize=False,
                include_paths=args.include_dirs,
                defines=compile_defines,
                use_system_cpp=args.use_system_cpp,
            )
            pres = cc.compile_file(src, None, preprocess_only=True)
            if not pres.success:
                for e in pres.errors:
                    print("Error:", e)
                return 1
            toks = cc.get_tokens(pres.assembly or "")
            out_t = args.dump_tokens_to or "pycc-tmp.tokens"
            with open(out_t, "w", encoding="utf-8") as f:
                for t in toks:
                    # Token has a useful __repr__/__str__ in this codebase.
                    f.write(str(t) + "\n")
            if args.verbose:
                print(f"[pycc] tokens: {src} -> {out_t}")
        except Exception as e:
            print(f"Error: {e}")
            return 1

    if args.dump_asm_only_to:
        if len(args.source) != 1:
            print("Error: --dump-asm-only-to currently supports exactly one input file")
            return 1
        # No conflict with output modes needed; we exit before compilation output handling.
        try:
            src = args.source[0]
            cc = Compiler(
                optimize=not args.no_opt,
                include_paths=args.include_dirs,
                defines=compile_defines,
                use_system_cpp=args.use_system_cpp,
            )
            res = cc.compile_file(src, args.dump_asm_only_to)
            if not res.success:
                for e in res.errors:
                    print("Error:", e)
                return 1
            if args.verbose:
                print(f"[pycc] asm: {src} -> {args.dump_asm_only_to}")
            return 0
        except Exception as e:
            print(f"Error: {e}")
            return 1

    if args.dump_asm or args.dump_asm_to:
        if len(args.source) != 1:
            print("Error: --dump-asm currently supports exactly one input file")
            return 1
        # Do not conflict with explicit output modes.
        if args.S or args.c or args.print_asm:
            print("Error: --dump-asm cannot be combined with -S/-c/--print-asm")
            return 1
        try:
            src = args.source[0]
            out_s = args.dump_asm_to or "pycc-tmp.s"
            cc = Compiler(
                optimize=not args.no_opt,
                include_paths=args.include_dirs,
                defines=compile_defines,
                use_system_cpp=args.use_system_cpp,
            )
            res = cc.compile_file(src, out_s)
            if not res.success:
                for e in res.errors:
                    print("Error:", e)
                return 1
            if args.verbose:
                print(f"[pycc] asm: {src} -> {out_s}")
        except Exception as e:
            print(f"Error: {e}")
            return 1

    if args.dump_ir_only_to:
        if len(args.source) != 1:
            print("Error: --dump-ir-only-to currently supports exactly one input file")
            return 1
        try:
            # Build IR directly to avoid changing the main compiler pipeline.
            src = args.source[0]
            c = Compiler(
                optimize=not args.no_opt,
                include_paths=args.include_dirs,
                defines=compile_defines,
                use_system_cpp=args.use_system_cpp,
            )
            pres = c.compile_file(src, None, preprocess_only=True)
            if not pres.success:
                for e in pres.errors:
                    print("Error:", e)
                return 1
            text = pres.assembly or ""

            tokens = c.get_tokens(text)
            ast = c.get_ast(tokens)
            sema_ctx, _ = c.analyze_semantics(ast)
            ir_list = c.get_ir(ast, sema_ctx=sema_ctx)

            with open(args.dump_ir_only_to, "w", encoding="utf-8") as f:
                for ins in ir_list:
                    f.write(str(ins) + "\n")
            if args.verbose:
                print(f"[pycc] ir: {src} -> {args.dump_ir_only_to}")
            return 0
        except Exception as e:
            print(f"Error: {e}")
            return 1

    if args.dump_ir or args.dump_ir_to:
        if len(args.source) != 1:
            print("Error: --dump-ir currently supports exactly one input file")
            return 1
        try:
            # Build IR directly to avoid changing the main compiler pipeline.
            src = args.source[0]
            c = Compiler(
                optimize=not args.no_opt,
                include_paths=args.include_dirs,
                defines=compile_defines,
                use_system_cpp=args.use_system_cpp,
            )
            # Preprocess
            pres = c.compile_file(src, None, preprocess_only=True)
            if not pres.success:
                for e in pres.errors:
                    print("Error:", e)
                return 1
            text = pres.assembly or ""

            tokens = c.get_tokens(text)
            ast = c.get_ast(tokens)
            sema_ctx, _ = c.analyze_semantics(ast)
            ir_list = c.get_ir(ast, sema_ctx=sema_ctx)

            out_ir = args.dump_ir_to or "pycc-tmp.ir"
            with open(out_ir, "w", encoding="utf-8") as f:
                for ins in ir_list:
                    f.write(str(ins) + "\n")
            if args.verbose:
                print(f"[pycc] ir: {src} -> {out_ir}")
        except Exception as e:
            print(f"Error: {e}")
            return 1

    if args.dump_preprocessed_only_to:
        # Convenience mode: dump preprocessed output to a chosen file and exit.
        if len(args.source) != 1:
            print("Error: --dump-preprocessed-only-to currently supports exactly one input file")
            return 1
        try:
            c = Compiler(
                optimize=False,
                include_paths=args.include_dirs,
                defines=compile_defines,
                use_system_cpp=args.use_system_cpp,
            )
            res = c.compile_file(args.source[0], None, preprocess_only=True)
            if not res.success:
                for e in res.errors:
                    print("Error:", e)
                return 1
            with open(args.dump_preprocessed_only_to, "w", encoding="utf-8") as f:
                f.write(res.assembly or "")
            if args.verbose:
                print(f"[pycc] preprocessed: {args.source[0]} -> {args.dump_preprocessed_only_to}")
            return 0
        except Exception as e:
            print(f"Error: {e}")
            return 1

    if args.dump_preprocessed or args.dump_preprocessed_to:
        if len(args.source) != 1:
            print("Error: --dump-preprocessed currently supports exactly one input file")
            return 1
        try:
            c = Compiler(
                optimize=False,
                include_paths=args.include_dirs,
                defines=compile_defines,
                use_system_cpp=args.use_system_cpp,
            )
            # Reuse compile_file preprocessing path but stop after preprocessing.
            res = c.compile_file(args.source[0], None, preprocess_only=True)
            if not res.success:
                for e in res.errors:
                    print("Error:", e)
                return 1
            out_i = args.dump_preprocessed_to or "pycc-tmp.i"
            with open(out_i, "w", encoding="utf-8") as f:
                f.write(res.assembly or "")
            if args.verbose:
                print(f"[pycc] preprocessed: {args.source[0]} -> {out_i}")
        except Exception as e:
            print(f"Error: {e}")
            return 1

    compiler = Compiler(
        optimize=not args.no_opt,
        include_paths=args.include_dirs,
        defines=compile_defines,
        use_system_cpp=args.use_system_cpp,
    )

    # Single input: preserve previous behavior.
    if len(args.source) == 1:
        # gcc-style: '-' means read source from stdin.
        # But allow `-- -` to refer to a literal file named '-'.
        if stdin_dash_allowed and args.source[0] == "-":
            try:
                src_text = sys.stdin.read()
            except Exception as e:
                print(f"Error: cannot read stdin: {e}")
                return 1
            # Write to a temporary .c file so we can keep using compile_file.
            try:
                fd, tmp_c = tempfile.mkstemp(prefix="pycc_stdin_", suffix=".c")
                os.close(fd)
                with open(tmp_c, "w", encoding="utf-8") as f:
                    f.write(src_text)
            except OSError as e:
                print(f"Error: cannot create temp source file: {e}")
                return 1
            try:
                if args.verbose:
                    print(f"[pycc] compile: <stdin> -> {args.output}")
                result = compiler.compile_file(tmp_c, args.output)
            finally:
                try:
                    os.unlink(tmp_c)
                except OSError:
                    pass
        else:
            if args.verbose:
                print(f"[pycc] compile: {args.source[0]} -> {args.output}")
            result = compiler.compile_file(args.source[0], args.output)
        if not result.success:
            for e in result.errors:
                print("Error:", e)
            return 1
        if args.print_asm:
            try:
                sys.stdout.write(open(args.output, "r", encoding="utf-8").read())
            except OSError as e:
                print(f"Error: cannot read {args.output}: {e}")
                return 1
            finally:
                try:
                    if temp_asm_path and not args.save_temps:
                        os.unlink(temp_asm_path)
                except OSError:
                    pass
            return 0

        print("Done:", args.output)
        return 0

    # Multi-input subset: compile each source to a temporary .o and then link.
    # Supports only producing an executable output.
    if args.output.endswith(".s") or args.output.endswith(".o"):
        print("Error: multi-input mode only supports linking to an executable (-o a.out)")
        return 1

    obj_paths: List[str] = []
    with tempfile.TemporaryDirectory(prefix="pycc_mf_") as td:
        for i, src in enumerate(args.source):
            obj = os.path.join(td, f"tu{i}.o")
            if args.verbose:
                print(f"[pycc] compile: {src} -> {obj}")
            res = compiler.compile_file(src, obj)
            if not res.success:
                for e in res.errors:
                    print("Error:", e)
                return 1
            obj_paths.append(obj)

        # Link using system gcc.
        if args.verbose:
            print(f"[pycc] link: gcc -no-pie -o {args.output} {' '.join(obj_paths)}")
        link = subprocess.run(["gcc", "-no-pie", "-o", args.output, *obj_paths])
        if link.returncode != 0:
            print("Error: link failed")
            return 1

    print("Done:", args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
