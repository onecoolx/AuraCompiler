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
from typing import List, Optional

import os
import tempfile
import subprocess

from pycc.compiler import Compiler


def main(argv: Optional[List[str]] = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    ap = argparse.ArgumentParser(prog="pycc", description="AuraCompiler CLI")
    ap.add_argument("source", nargs="+", help="Input C source file(s)")
    ap.add_argument("-o", dest="output", required=True, help="Output: .s, .o, or executable")
    ap.add_argument("--no-opt", action="store_true", help="Disable optimizations")
    args = ap.parse_args(argv)

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
