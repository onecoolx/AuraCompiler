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
        define_re = re.compile(r"^\s*#\s*define\s+([A-Za-z_][A-Za-z0-9_]*)\s*(.*)$")
        if0_re = re.compile(r"^\s*#\s*if\s+0\s*$")
        if1_re = re.compile(r"^\s*#\s*if\s+1\s*$")
        else_re = re.compile(r"^\s*#\s*else\s*$")
        elif0_re = re.compile(r"^\s*#\s*elif\s+0\s*$")
        elif1_re = re.compile(r"^\s*#\s*elif\s+1\s*$")
        endif_re = re.compile(r"^\s*#\s*endif\s*$")

        def _preprocess_file(path: str, stack: List[str], macros: dict[str, str]) -> str:
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
            # Track conditional inclusion state.
            # include_stack entries are booleans: whether the current level is active.
            include_stack: List[bool] = [True]
            # For each nested #if-group, track whether any previous branch has been taken.
            # Value is meaningful only when len(include_stack) > 1.
            taken_stack: List[bool] = []
            for line in raw:
                # Minimal conditional compilation subset: #if 0 ... #endif
                if if0_re.match(line):
                    parent = include_stack[-1]
                    include_stack.append(parent and False)
                    taken_stack.append(False)
                    continue
                if if1_re.match(line):
                    parent = include_stack[-1]
                    include_stack.append(parent and True)
                    taken_stack.append(parent and True)
                    continue

                if elif0_re.match(line) or elif1_re.match(line):
                    if len(include_stack) <= 1:
                        continue
                    parent = include_stack[-2]
                    already = taken_stack[-1]
                    cond_true = bool(elif1_re.match(line))
                    new_active = parent and (not already) and cond_true
                    include_stack[-1] = new_active
                    taken_stack[-1] = already or new_active
                    continue

                if else_re.match(line):
                    if len(include_stack) > 1:
                        parent = include_stack[-2]
                        already = taken_stack[-1] if taken_stack else False
                        new_active = parent and (not already)
                        include_stack[-1] = new_active
                        if taken_stack:
                            taken_stack[-1] = already or new_active
                    continue
                if endif_re.match(line):
                    if len(include_stack) > 1:
                        include_stack.pop()
                        if taken_stack:
                            taken_stack.pop()
                    continue
                if not include_stack[-1]:
                    continue

                md = define_re.match(line)
                if md:
                    name = md.group(1)
                    val = md.group(2).rstrip("\n")
                    macros[name] = val.strip()
                    # Do not emit #define lines.
                    continue
                m = include_re.match(line)
                if m:
                    inc_name = m.group(1)
                    inc_path = os.path.join(base_dir, inc_name)
                    out_lines.append(_preprocess_file(inc_path, stack, macros))
                    continue

                # Very small subset: object-like macro replacement on identifier boundaries.
                expanded = line
                for k, v in macros.items():
                    expanded = re.sub(rf"\b{re.escape(k)}\b", v, expanded)
                out_lines.append(expanded)

            stack.pop()
            return "".join(out_lines)

        src = args.source[0]
        try:
            text = _preprocess_file(src, [], {})
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
