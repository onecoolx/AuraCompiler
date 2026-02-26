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

    ap = argparse.ArgumentParser(prog="pycc", description="AuraCompiler CLI")
    ap.add_argument("source", nargs="+", help="Input C source file(s)")
    ap.add_argument("-E", action="store_true", help="Preprocess only (subset: passthrough)")
    ap.add_argument(
        "-D",
        dest="defines",
        action="append",
        default=[],
        metavar="NAME[=VALUE]",
        help="Define a macro for preprocessing (subset; -E only)",
    )
    ap.add_argument(
        "-U",
        dest="undefines",
        action="append",
        default=[],
        metavar="NAME",
        help="Undefine a macro for preprocessing (subset; -E only)",
    )
    ap.add_argument("-o", dest="output", required=False, help="Output: .s, .o, or executable")
    ap.add_argument("--no-opt", action="store_true", help="Disable optimizations")
    args = ap.parse_args(argv)

    # Preprocessor stage (subset): passthrough the first input.
    if args.E:
        # For now, only support a single input in -E mode.
        if len(args.source) != 1:
            print("Error: -E currently supports exactly one input file")
            return 1

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
            pp = Preprocessor()
            res = pp.preprocess(src, initial_macros=initial_macros)
            if not res.success:
                for e in (res.errors or []):
                    print(f"Error: {e}")
                return 1
            text = res.text
        except Exception as e:
            print(f"Error: {e}")
            return 1
        if args.output:
            try:
                open(args.output, "w", encoding="utf-8").write(text)
            except OSError as e:
                print(f"Error: cannot write {args.output}: {e}")
                return 1
        else:
            sys.stdout.write(text)
        return 0

    if not args.output:
        print("Error: -o is required unless -E is used")
        return 1

    compiler = Compiler(optimize=not args.no_opt)

    # Single input: preserve previous behavior.
    if len(args.source) == 1:
        result = compiler.compile_file(args.source[0], args.output)
        if not result.success:
            for e in result.errors:
                print("Error:", e)
            return 1
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
            res = compiler.compile_file(src, obj)
            if not res.success:
                for e in res.errors:
                    print("Error:", e)
                return 1
            obj_paths.append(obj)

        # Link using system gcc.
        link = subprocess.run(["gcc", "-no-pie", "-o", args.output, *obj_paths])
        if link.returncode != 0:
            print("Error: link failed")
            return 1

    print("Done:", args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
