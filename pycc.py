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

import re

from pycc.compiler import Compiler


def main(argv: Optional[List[str]] = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    ap = argparse.ArgumentParser(prog="pycc", description="AuraCompiler CLI")
    ap.add_argument("source", nargs="+", help="Input C source file(s)")
    ap.add_argument("-E", action="store_true", help="Preprocess only (subset: passthrough)")
    ap.add_argument("-o", dest="output", required=False, help="Output: .s, .o, or executable")
    ap.add_argument("--no-opt", action="store_true", help="Disable optimizations")
    args = ap.parse_args(argv)

    # Preprocessor stage (subset): passthrough the first input.
    if args.E:
        # For now, only support a single input in -E mode.
        if len(args.source) != 1:
            print("Error: -E currently supports exactly one input file")
            return 1

        include_re = re.compile(r"^\s*#\s*include\s*\"([^\"]+)\"\s*$")

        def _preprocess_file(path: str, stack: List[str]) -> str:
            abspath = os.path.abspath(path)
            if abspath in stack:
                raise RuntimeError(f"include cycle detected: {abspath}")
            stack.append(abspath)
            try:
                raw = open(abspath, "r", encoding="utf-8").read().splitlines(True)
            except OSError as e:
                raise RuntimeError(f"cannot read {path}: {e}")

            out_lines: List[str] = []
            base_dir = os.path.dirname(abspath)
            for line in raw:
                m = include_re.match(line)
                if m:
                    inc_name = m.group(1)
                    inc_path = os.path.join(base_dir, inc_name)
                    out_lines.append(_preprocess_file(inc_path, stack))
                    continue
                out_lines.append(line)

            stack.pop()
            return "".join(out_lines)

        src = args.source[0]
        try:
            text = _preprocess_file(src, [])
        except RuntimeError as e:
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
