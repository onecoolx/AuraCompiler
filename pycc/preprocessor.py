from __future__ import annotations

import os
import re
import subprocess
import shutil
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Union


def _parse_gcc_include_paths(gcc_stderr: str) -> List[str]:
    paths: List[str] = []
    in_block = False
    for raw in gcc_stderr.splitlines():
        line = raw.rstrip("\n")
        if "#include <...> search starts here:" in line or "#include \"...\" search starts here:" in line:
            in_block = True
            continue
        if in_block and "End of search list." in line:
            break
        if not in_block:
            continue

        s = line.strip()
        if not s:
            continue
        if s.startswith("(") and s.endswith(")"):
            # e.g. "(framework directory)"
            continue
        # Drop trailing annotations like "(sysroot)" or "(framework directory)".
        if " (" in s and s.endswith(")"):
            s = s.split(" (", 1)[0].strip()
        paths.append(s)
    return paths


def _probe_system_include_paths() -> List[str]:
    gcc = shutil.which("gcc")
    if not gcc:
        return []
    sysroot = ""
    try:
        p_sysroot = subprocess.run(
            [gcc, "-print-sysroot"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if p_sysroot.returncode == 0:
            sysroot = (p_sysroot.stdout or "").strip()
    except Exception:
        sysroot = ""

    # Ask gcc for its include search list. This is more robust across distros than hardcoding.
    p = subprocess.run(
        [gcc, "-E", "-Wp,-v", "-"],
        input="\n",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    # gcc prints include search paths to stderr.
    paths = _parse_gcc_include_paths(p.stderr)

    # If gcc reports a sysroot, expand relative include entries under it.
    # Some toolchains print paths like "include" or "usr/include".
    if sysroot and os.path.isdir(sysroot):
        expanded: List[str] = []
        for d in paths:
            if d.startswith("/"):
                expanded.append(d)
                continue
            cand = os.path.join(sysroot, d)
            expanded.append(cand)
        paths = expanded

    # De-dup while preserving order.
    seen = set()
    out: List[str] = []
    for d in paths:
        if d in seen:
            continue
        seen.add(d)
        out.append(d)
    return out


@dataclass
class PreprocessResult:
    success: bool
    text: str = ""
    errors: List[str] = None

    def __post_init__(self) -> None:
        if self.errors is None:
            self.errors = []


class Preprocessor:
    """Very small preprocessor for AuraCompiler.

    Current subset (used by `pycc.py -E`):
    - passthrough of source text
    - local includes: #include "file"
    - object-like defines: #define NAME value
    - conditionals: #if 0/1, #elif 0/1, #else, #endif

    Not supported:
    - angle-bracket includes, include paths
    - function-like macros
    - expression evaluation in #if
    """

    def __init__(self, *, include_paths: Optional[List[str]] = None) -> None:
        self._include_quote_re = re.compile(r"^\s*#\s*include\s*\"([^\"]+)\"\s*$")
        self._include_angle_re = re.compile(r"^\s*#\s*include\s*<([^>]+)>\s*$")
        self._define_re = re.compile(r"^\s*#\s*define\s+([A-Za-z_][A-Za-z0-9_]*)\s*(.*)$")
        self._undef_re = re.compile(r"^\s*#\s*undef\s+([A-Za-z_][A-Za-z0-9_]*)\s*$")
        self._ifdef_re = re.compile(r"^\s*#\s*ifdef\s+([A-Za-z_][A-Za-z0-9_]*)\s*$")
        self._ifndef_re = re.compile(r"^\s*#\s*ifndef\s+([A-Za-z_][A-Za-z0-9_]*)\s*$")
        self._if_name_re = re.compile(r"^\s*#\s*if\s+([A-Za-z_][A-Za-z0-9_]*)\s*$")
        self._if0_re = re.compile(r"^\s*#\s*if\s+0\s*$")
        self._if1_re = re.compile(r"^\s*#\s*if\s+1\s*$")
        self._elif0_re = re.compile(r"^\s*#\s*elif\s+0\s*$")
        self._elif1_re = re.compile(r"^\s*#\s*elif\s+1\s*$")
        self._elif_name_re = re.compile(r"^\s*#\s*elif\s+([A-Za-z_][A-Za-z0-9_]*)\s*$")
        self._else_re = re.compile(r"^\s*#\s*else\s*$")
        self._endif_re = re.compile(r"^\s*#\s*endif\s*$")
        user_paths = [os.path.abspath(p) for p in (include_paths or [])]
        probed = [p for p in _probe_system_include_paths() if os.path.isdir(p)]
        # Fallback defaults if probing fails.
        fallback_defaults = [
            "/usr/local/include",
            "/usr/include",
            "/usr/include/x86_64-linux-gnu",
        ]
        fallback = [p for p in fallback_defaults if os.path.isdir(p)]
        sys_paths = probed or fallback
        self._include_paths = user_paths + sys_paths

        # Function-like macro storage: NAME -> (param_names, body)
        self._fn_macros: Dict[str, Tuple[List[str], str]] = {}

    def _eval_cond_01(self, name: str, macros: Dict[str, str]) -> bool:
        """Evaluate a very small #if/#elif condition.

        Supported subset:
        - literal 0/1
        - single identifier NAME, treated as:
          - false if undefined
          - true/false if defined and expands to exactly 0/1
          - error otherwise
        """

        if name == "0":
            return False
        if name == "1":
            return True
        if name not in macros:
            return False
        repl = macros[name].strip()
        if repl == "0":
            return False
        if repl == "1":
            return True
        raise RuntimeError(f"unsupported #if expression: {name} expands to {repl!r}")

    def preprocess(self, path: str, *, initial_macros: Optional[Dict[str, str]] = None) -> PreprocessResult:
        try:
            macros = dict(initial_macros or {})
            text = self._preprocess_file(path, stack=[], macros=macros)
            return PreprocessResult(success=True, text=text)
        except RuntimeError as e:
            return PreprocessResult(success=False, errors=[str(e)])

    def _preprocess_file(self, path: str, stack: List[str], macros: Dict[str, str]) -> str:
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

        include_stack: List[bool] = [True]
        taken_stack: List[bool] = []

        for line in raw:
            # Conditionals
            if self._if0_re.match(line):
                parent = include_stack[-1]
                include_stack.append(parent and False)
                taken_stack.append(False)
                continue
            if self._if1_re.match(line):
                parent = include_stack[-1]
                include_stack.append(parent and True)
                taken_stack.append(parent and True)
                continue
            mifname = self._if_name_re.match(line)
            if mifname:
                parent = include_stack[-1]
                name = mifname.group(1)
                cond_true = self._eval_cond_01(name, macros)
                include_stack.append(parent and cond_true)
                taken_stack.append(parent and cond_true)
                continue
            mifdef = self._ifdef_re.match(line)
            if mifdef:
                parent = include_stack[-1]
                name = mifdef.group(1)
                cond_true = name in macros
                include_stack.append(parent and cond_true)
                taken_stack.append(parent and cond_true)
                continue
            mifndef = self._ifndef_re.match(line)
            if mifndef:
                parent = include_stack[-1]
                name = mifndef.group(1)
                cond_true = name not in macros
                include_stack.append(parent and cond_true)
                taken_stack.append(parent and cond_true)
                continue
            if self._elif0_re.match(line) or self._elif1_re.match(line):
                if len(include_stack) <= 1:
                    continue
                parent = include_stack[-2]
                already = taken_stack[-1]
                cond_true = bool(self._elif1_re.match(line))
                new_active = parent and (not already) and cond_true
                include_stack[-1] = new_active
                taken_stack[-1] = already or new_active
                continue
            melifname = self._elif_name_re.match(line)
            if melifname:
                if len(include_stack) <= 1:
                    continue
                parent = include_stack[-2]
                already = taken_stack[-1]
                name = melifname.group(1)
                cond_true = self._eval_cond_01(name, macros)
                new_active = parent and (not already) and cond_true
                include_stack[-1] = new_active
                taken_stack[-1] = already or new_active
                continue
            if self._else_re.match(line):
                if len(include_stack) > 1:
                    parent = include_stack[-2]
                    already = taken_stack[-1] if taken_stack else False
                    new_active = parent and (not already)
                    include_stack[-1] = new_active
                    if taken_stack:
                        taken_stack[-1] = already or new_active
                continue
            if self._endif_re.match(line):
                if len(include_stack) > 1:
                    include_stack.pop()
                    if taken_stack:
                        taken_stack.pop()
                continue

            if not include_stack[-1]:
                continue

            # Defines
            md = self._define_re.match(line)
            if md:
                name = md.group(1)
                val = md.group(2).rstrip("\n")
                # Function-like macro: #define F(x) ...
                # NOTE: very small subset; no variadics, no comments handling, no multiline.
                mfn = re.match(r"^\s*\(([^)]*)\)\s*(.*)$", val)
                if mfn is not None:
                    params_raw = mfn.group(1).strip()
                    body = mfn.group(2)
                    if params_raw == "":
                        params = []
                    else:
                        params = [p.strip() for p in params_raw.split(",")]
                    for p in params:
                        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", p):
                            raise RuntimeError(f"unsupported function-like macro params for {name}")
                    self._fn_macros[name] = (params, body.strip())
                    macros.pop(name, None)
                else:
                    macros[name] = val.strip()
                    self._fn_macros.pop(name, None)
                continue

            mu = self._undef_re.match(line)
            if mu:
                name = mu.group(1)
                macros.pop(name, None)
                self._fn_macros.pop(name, None)
                continue

            # Includes (subset)
            miq = self._include_quote_re.match(line)
            if miq:
                inc_name = miq.group(1)
                search_paths = [base_dir, *self._include_paths]
                inc_path = self._resolve_include(inc_name, search_paths)
                out_lines.append(self._preprocess_file(inc_path, stack, macros))
                continue

            mia = self._include_angle_re.match(line)
            if mia:
                inc_name = mia.group(1).strip()
                search_paths = [*self._include_paths]
                inc_path = self._resolve_include(inc_name, search_paths)
                out_lines.append(self._preprocess_file(inc_path, stack, macros))
                continue

            out_lines.append(self._expand_line(line, macros))

        stack.pop()
        return "".join(out_lines)

    def _expand_line(self, line: str, macros: Dict[str, str]) -> str:
        # Expand function-like invocations first (best-effort), then object-like macros.
        expanded = line
        expanded = self._expand_function_like_macros(expanded, macros)
        for k, v in macros.items():
            expanded = re.sub(rf"\b{re.escape(k)}\b", lambda _m, _v=v: _v, expanded)
        return expanded

    def _expand_function_like_macros(self, text: str, macros: Dict[str, str]) -> str:
        # Very small subset expansion:
        # - only expands NAME(arglist) with balanced parentheses in arglist
        # - arguments are split by commas at paren depth 0
        # - supports nested expansions by iterating until no change (cap iterations)
        out = text
        for _ in range(20):
            changed = False
            for name, (params, body) in list(self._fn_macros.items()):
                # Find a call site "NAME(" and expand the first one found, repeatedly.
                idx = 0
                while True:
                    m = re.search(rf"\b{re.escape(name)}\s*\(", out[idx:])
                    if not m:
                        break
                    call_start = idx + m.start()
                    paren_start = idx + m.end() - 1  # points at '('
                    arg_text, paren_end = self._extract_paren_group(out, paren_start)
                    if paren_end is None:
                        break

                    args = self._split_args(arg_text)
                    if len(args) != len(params):
                        raise RuntimeError(
                            f"unsupported macro invocation: {name} expects {len(params)} args, got {len(args)}"
                        )
                    repl = body
                    # Subset ordering:
                    # - stringize must see the original param names (#x)
                    # - token paste must see param names to combine (a##b)
                    # We therefore expand these operators per-parameter first,
                    # then substitute the remaining plain params.
                    for p, a in zip(params, args):
                        repl = self._apply_stringize(repl, p, a)
                    # Do parameter substitution first (so a##b turns into x##y),
                    # then do token-paste removal.
                    for p, a in zip(params, args):
                        repl = re.sub(rf"\b{re.escape(p)}\b", a, repl)
                    repl = self._apply_token_paste_simple(repl)
                    # Recursively expand inside the replacement on subsequent passes.
                    out = out[:call_start] + repl + out[paren_end + 1 :]
                    changed = True
                    idx = call_start + len(repl)
            if not changed:
                return out
        return out

    def _apply_stringize(self, body: str, param: str, arg: str) -> str:
        # Very small subset of stringize (#param):
        # - no whitespace normalization
        # - no escaping
        # - wraps raw argument text in double quotes
        # Only match `#param` when '#' is not part of '##'.
        return re.sub(
            rf"(?<!#)#\s*{re.escape(param)}\b",
            lambda _m: '"' + arg.strip() + '"',
            body,
        )

    def _apply_token_paste_simple(self, body: str) -> str:
        # Very small subset: after params are substituted, just delete the operator.
        return re.sub(r"\s*##\s*", "", body)

    def _extract_paren_group(self, s: str, lparen_index: int) -> Tuple[str, Union[int, None]]:
        if lparen_index < 0 or lparen_index >= len(s) or s[lparen_index] != "(":
            return "", None
        depth = 0
        i = lparen_index
        start = lparen_index + 1
        while i < len(s):
            ch = s[i]
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    return s[start:i], i
            i += 1
        return "", None

    def _split_args(self, arg_text: str) -> List[str]:
        args: List[str] = []
        cur: List[str] = []
        depth = 0
        for ch in arg_text:
            if ch == "," and depth == 0:
                args.append("".join(cur).strip())
                cur = []
                continue
            if ch == "(":
                depth += 1
            elif ch == ")":
                if depth > 0:
                    depth -= 1
            cur.append(ch)
        tail = "".join(cur).strip()
        if tail or arg_text.strip() == "":
            args.append(tail)
        return args

    def _resolve_include(self, inc_name: str, search_paths: List[str]) -> str:
        for d in search_paths:
            cand = os.path.abspath(os.path.join(d, inc_name))
            if os.path.isfile(cand):
                return cand
        shown = ", ".join(search_paths[:10])
        more = "" if len(search_paths) <= 10 else f" (+{len(search_paths) - 10} more)"
        raise RuntimeError(f"cannot find include: {inc_name} (searched: {shown}{more})")
