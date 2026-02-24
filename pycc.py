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

from pycc.compiler import Compiler


def main(argv: Optional[List[str]] = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    ap = argparse.ArgumentParser(prog="pycc", description="AuraCompiler CLI")
    ap.add_argument("source", help="Input C source file")
    ap.add_argument("-o", dest="output", required=True, help="Output: .s, .o, or executable")
    ap.add_argument("--no-opt", action="store_true", help="Disable optimizations")
    args = ap.parse_args(argv)

    compiler = Compiler(optimize=not args.no_opt)
    result = compiler.compile_file(args.source, args.output)
    if not result.success:
        for e in result.errors:
            print("Error:", e)
        return 1
    print("Done:", args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
