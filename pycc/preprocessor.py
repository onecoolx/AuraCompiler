from __future__ import annotations

import os
import re
import subprocess
import shutil
from datetime import datetime
from dataclasses import dataclass, field
from typing import Dict, FrozenSet, List, Optional, Set, Tuple, Union


# ---------------------------------------------------------------------------
# PPToken and token-based macro expansion infrastructure (C89 §3.8)
# ---------------------------------------------------------------------------

@dataclass
class PPToken:
    """Preprocessing token with hide-set for macro expansion."""
    kind: str  # 'ident', 'number', 'string', 'char', 'punct', 'space', 'other'
    text: str
    hide_set: FrozenSet[str] = field(default_factory=frozenset)
    line: int = 0
    column: int = 0


@dataclass
class MacroDef:
    """Macro definition for the token-based expander."""
    name: str
    is_function_like: bool = False
    params: List[str] = field(default_factory=list)
    is_variadic: bool = False
    replacement: List[PPToken] = field(default_factory=list)


class PPTokenizer:
    """Tokenize source text into PPToken stream."""

    _PUNCT = frozenset('(){}[];,~?') | frozenset([
        '...', '<<=', '>>=', '##',
        '<<', '>>', '<=', '>=', '==', '!=', '&&', '||',
        '+=', '-=', '*=', '/=', '%=', '&=', '|=', '^=',
        '->', '++', '--',
        '+', '-', '*', '/', '%', '&', '|', '^', '!',
        '<', '>', '=', '.', '#',
    ])

    def tokenize(self, text: str) -> List[PPToken]:
        tokens: List[PPToken] = []
        i, n = 0, len(text)
        line, col = 1, 1
        while i < n:
            c = text[i]
            # whitespace (not newline)
            if c in ' \t':
                j = i
                while j < n and text[j] in ' \t':
                    j += 1
                tokens.append(PPToken('space', text[i:j], line=line, column=col))
                col += j - i
                i = j
                continue
            if c == '\n':
                tokens.append(PPToken('space', '\n', line=line, column=col))
                line += 1
                col = 1
                i += 1
                continue
            # identifier
            if c.isalpha() or c == '_':
                j = i
                while j < n and (text[j].isalnum() or text[j] == '_'):
                    j += 1
                tokens.append(PPToken('ident', text[i:j], line=line, column=col))
                col += j - i
                i = j
                continue
            # number (pp-number: digit or .digit, then digits/letters/dots/signs)
            if c.isdigit() or (c == '.' and i + 1 < n and text[i + 1].isdigit()):
                j = i
                while j < n and (text[j].isalnum() or text[j] in '.+-'):
                    if text[j] in '+-' and j > i and text[j - 1] not in 'eEpP':
                        break
                    j += 1
                tokens.append(PPToken('number', text[i:j], line=line, column=col))
                col += j - i
                i = j
                continue
            # string literal
            if c == '"':
                j = i + 1
                while j < n and text[j] != '"':
                    if text[j] == '\\' and j + 1 < n:
                        j += 1
                    j += 1
                j = min(j + 1, n)
                tokens.append(PPToken('string', text[i:j], line=line, column=col))
                col += j - i
                i = j
                continue
            # char literal
            if c == "'":
                j = i + 1
                while j < n and text[j] != "'":
                    if text[j] == '\\' and j + 1 < n:
                        j += 1
                    j += 1
                j = min(j + 1, n)
                tokens.append(PPToken('char', text[i:j], line=line, column=col))
                col += j - i
                i = j
                continue
            # multi-char punctuation (try longest match)
            matched = False
            for plen in (3, 2, 1):
                candidate = text[i:i + plen]
                if candidate in self._PUNCT:
                    tokens.append(PPToken('punct', candidate, line=line, column=col))
                    col += plen
                    i += plen
                    matched = True
                    break
            if matched:
                continue
            # other
            tokens.append(PPToken('other', c, line=line, column=col))
            col += 1
            i += 1
        return tokens


class MacroExpander:
    """Hide-set based macro expander (C89 §3.8.3).

    Implements the standard algorithm:
    1. Scan token sequence left-to-right
    2. When an identifier matches a macro name and is not in its own hide-set:
       - Object-like: substitute replacement, add macro name to hide-set, rescan
       - Function-like: collect args, expand args, substitute, add to hide-set, rescan
    3. Stringize (#) and token-paste (##) are handled during substitution
    """

    def __init__(self, macros: Optional[Dict[str, MacroDef]] = None):
        self.macros: Dict[str, MacroDef] = macros or {}

    def expand(self, tokens: List[PPToken]) -> List[PPToken]:
        """Expand all macros in the token sequence."""
        result: List[PPToken] = []
        i = 0
        while i < len(tokens):
            tok = tokens[i]
            if (tok.kind == 'ident' and tok.text in self.macros
                    and tok.text not in tok.hide_set):
                macro = self.macros[tok.text]
                if macro.is_function_like:
                    args, end = self._collect_args(tokens, i + 1)
                    if args is not None:
                        expanded = self._expand_function_macro(macro, args, tok.hide_set)
                        result.extend(expanded)
                        i = end + 1
                        continue
                else:
                    expanded = self._expand_object_macro(macro, tok.hide_set)
                    result.extend(expanded)
                    i += 1
                    continue
            result.append(tok)
            i += 1
        return result

    def _expand_object_macro(self, macro: MacroDef, caller_hs: FrozenSet[str]) -> List[PPToken]:
        new_hs = caller_hs | {macro.name}
        replacement = [
            PPToken(t.kind, t.text, t.hide_set | new_hs, t.line, t.column)
            for t in macro.replacement
        ]
        return self.expand(replacement)

    def _expand_function_macro(self, macro: MacroDef, args: List[List[PPToken]],
                                caller_hs: FrozenSet[str]) -> List[PPToken]:
        # 1. Expand each argument (for non-# / non-## operands)
        expanded_args = [self.expand(arg) for arg in args]
        # 2. Substitute into replacement list
        replacement = self._substitute(macro, args, expanded_args)
        # 3. Process ## token paste
        replacement = self._process_paste(replacement)
        # 4. Add hide-set and rescan
        new_hs = caller_hs | {macro.name}
        replacement = [
            PPToken(t.kind, t.text, t.hide_set | new_hs, t.line, t.column)
            for t in replacement
        ]
        return self.expand(replacement)

    def _substitute(self, macro: MacroDef, raw_args: List[List[PPToken]],
                     expanded_args: List[List[PPToken]]) -> List[PPToken]:
        """Substitute parameters in replacement list."""
        result: List[PPToken] = []
        repl = macro.replacement
        i = 0
        while i < len(repl):
            tok = repl[i]
            # # stringize
            if tok.kind == 'punct' and tok.text == '#' and i + 1 < len(repl):
                next_tok = repl[i + 1]
                if next_tok.kind == 'ident' and next_tok.text in macro.params:
                    idx = macro.params.index(next_tok.text)
                    arg = raw_args[idx] if idx < len(raw_args) else []
                    s = self._stringize(arg)
                    result.append(PPToken('string', s, line=tok.line, column=tok.column))
                    i += 2
                    continue
            # Parameter substitution
            if tok.kind == 'ident' and tok.text in macro.params:
                idx = macro.params.index(tok.text)
                # Check if adjacent to ##
                is_paste = False
                if i > 0 and repl[i - 1].kind == 'punct' and repl[i - 1].text == '##':
                    is_paste = True
                if i + 1 < len(repl) and repl[i + 1].kind == 'punct' and repl[i + 1].text == '##':
                    is_paste = True
                if is_paste:
                    arg = raw_args[idx] if idx < len(raw_args) else []
                else:
                    arg = expanded_args[idx] if idx < len(expanded_args) else []
                result.extend(arg)
                i += 1
                continue
            result.append(tok)
            i += 1
        return result

    def _process_paste(self, tokens: List[PPToken]) -> List[PPToken]:
        """Process ## token-paste operators.

        C89 §6.8.3.3: Each ## preprocessing token in the replacement list
        is deleted and the preceding preprocessing token is concatenated
        with the following preprocessing token.  If the result is not a
        valid preprocessing token, the behavior is undefined; we emit a
        diagnostic warning and keep the pasted text as-is.

        The pasted result is later rescanned during the normal expansion
        loop (step 4 in _expand_function_like).
        """
        result: List[PPToken] = []
        i = 0
        while i < len(tokens):
            if (tokens[i].kind == 'punct' and tokens[i].text == '##'
                    and result and i + 1 < len(tokens)):
                lhs = result.pop()
                rhs = tokens[i + 1]
                pasted_text = lhs.text + rhs.text
                # Determine kind of pasted token and validate
                if pasted_text.isidentifier() or (pasted_text.startswith('_') and pasted_text.replace('_', '').isalnum()):
                    kind = 'ident'
                elif pasted_text and (pasted_text[0].isdigit() or (pasted_text[0] == '.' and len(pasted_text) > 1 and pasted_text[1].isdigit())):
                    kind = 'number'
                elif pasted_text in ('(', ')', '[', ']', '{', '}', ',', ';', ':', '.',
                                     '+', '-', '*', '/', '%', '&', '|', '^', '~', '!',
                                     '<', '>', '=', '?', '#',
                                     '++', '--', '<<', '>>', '<=', '>=', '==', '!=',
                                     '&&', '||', '+=', '-=', '*=', '/=', '%=',
                                     '&=', '|=', '^=', '<<=', '>>=', '->', '##',
                                     '...'):
                    kind = 'punct'
                elif pasted_text.startswith('"') or pasted_text.startswith("'"):
                    kind = 'string' if pasted_text.startswith('"') else 'char'
                elif pasted_text == '':
                    # Empty paste: skip
                    i += 2
                    continue
                else:
                    kind = 'other'
                    import warnings
                    warnings.warn(
                        f'pasting "{lhs.text}" and "{rhs.text}" does not give a valid preprocessing token',
                        stacklevel=2,
                    )
                result.append(PPToken(kind, pasted_text,
                                       lhs.hide_set & rhs.hide_set,
                                       lhs.line, lhs.column))
                i += 2
                continue
            result.append(tokens[i])
            i += 1
        return result

    @staticmethod
    def _stringize(tokens: List[PPToken]) -> str:
        """Convert token sequence to a string literal (# operator).

        C89 §6.8.3.2: Each occurrence of whitespace between the argument's
        preprocessing tokens becomes a single space character.  Backslash
        and double-quote characters are escaped.  Tab and newline characters
        in the token text are preserved as their escape representations.
        """
        parts: List[str] = []
        for t in tokens:
            if t.kind == 'space':
                if parts and parts[-1] != ' ':
                    parts.append(' ')
            else:
                text = t.text
                # Escape backslash and double-quote in string/char literal tokens
                if t.kind in ('string', 'char'):
                    text = text.replace('\\', '\\\\').replace('"', '\\"')
                # Escape tab and newline characters in any token text
                text = text.replace('\t', '\\t').replace('\n', '\\n')
                # Escape unescaped double-quotes in non-string/char tokens
                if t.kind not in ('string', 'char'):
                    text = text.replace('\\', '\\\\').replace('"', '\\"')
                parts.append(text)
        inner = ''.join(parts).strip()
        return f'"{inner}"'

    def _collect_args(self, tokens: List[PPToken], start: int
                       ) -> Tuple[Optional[List[List[PPToken]]], int]:
        """Collect function-like macro arguments starting after the macro name.

        Returns (args, end_index) or (None, start) if no '(' follows.
        """
        # Skip whitespace to find '('
        i = start
        while i < len(tokens) and tokens[i].kind == 'space':
            i += 1
        if i >= len(tokens) or tokens[i].text != '(':
            return None, start
        i += 1  # skip '('
        args: List[List[PPToken]] = [[]]
        depth = 1
        while i < len(tokens) and depth > 0:
            if tokens[i].text == '(':
                depth += 1
                args[-1].append(tokens[i])
            elif tokens[i].text == ')':
                depth -= 1
                if depth > 0:
                    args[-1].append(tokens[i])
            elif tokens[i].text == ',' and depth == 1:
                args.append([])
            else:
                args[-1].append(tokens[i])
            i += 1
        # If only one empty arg, treat as zero args
        if len(args) == 1 and all(t.kind == 'space' for t in args[0]):
            args = []
        return args, i - 1


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
    - expression evaluation in #if (beyond NAME expanding to 0/1)
    - multiline macros, comments, full tokenization, variadics, etc.
    """

    def __init__(self, *, include_paths: Optional[List[str]] = None) -> None:
        self._include_quote_re = re.compile(r"^\s*#\s*include\s*\"([^\"]+)\"\s*$")
        self._include_angle_re = re.compile(r"^\s*#\s*include\s*<([^>]+)>\s*$")
        self._include_any_re = re.compile(r"^\s*#\s*include\s+(.+?)\s*$")
        self._include_next_re = re.compile(r"^\s*#\s*include_next\b.*$")
        self._define_re = re.compile(r"^\s*#\s*define\s+([A-Za-z_][A-Za-z0-9_]*)\s*(.*)$")
        self._undef_re = re.compile(r"^\s*#\s*undef\s+([A-Za-z_][A-Za-z0-9_]*)\s*$")
        self._ifdef_re = re.compile(r"^\s*#\s*ifdef\s+([A-Za-z_][A-Za-z0-9_]*)\s*$")
        self._ifndef_re = re.compile(r"^\s*#\s*ifndef\s+([A-Za-z_][A-Za-z0-9_]*)\s*$")
        self._if_name_re = re.compile(r"^\s*#\s*if\s+([A-Za-z_][A-Za-z0-9_]*)\s*$")
        self._if_defined_re = re.compile(
            r"^\s*#\s*if\s+(!\s*)?defined\s*(?:\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)|([A-Za-z_][A-Za-z0-9_]*))\s*$"
        )
        self._if_expr_re = re.compile(r"^\s*#\s*if\s+(.+?)\s*$")
        self._if0_re = re.compile(r"^\s*#\s*if\s+0\s*$")
        self._if1_re = re.compile(r"^\s*#\s*if\s+1\s*$")
        self._elif0_re = re.compile(r"^\s*#\s*elif\s+0\s*$")
        self._elif1_re = re.compile(r"^\s*#\s*elif\s+1\s*$")
        self._elif_name_re = re.compile(r"^\s*#\s*elif\s+([A-Za-z_][A-Za-z0-9_]*)\s*$")
        self._elif_defined_re = re.compile(
            r"^\s*#\s*elif\s+(!\s*)?defined\s*(?:\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)|([A-Za-z_][A-Za-z0-9_]*))\s*$"
        )
        self._elifdef_re = re.compile(r"^\s*#\s*elifdef\s+([A-Za-z_][A-Za-z0-9_]*)\s*$")
        self._elifndef_re = re.compile(r"^\s*#\s*elifndef\s+([A-Za-z_][A-Za-z0-9_]*)\s*$")
        self._elif_expr_re = re.compile(r"^\s*#\s*elif\s+(.+?)\s*$")
        self._else_re = re.compile(r"^\s*#\s*else\s*$")
        self._endif_re = re.compile(r"^\s*#\s*endif\s*$")
        self._line_re = re.compile(r"^\s*#\s*line\b.*$")
        self._pragma_once_re = re.compile(r"^\s*#\s*pragma\s+once\s*$")
        self._pragma_re = re.compile(r"^\s*#\s*pragma\b.*$")
        self._error_re = re.compile(r"^\s*#\s*error\b(.*)$")
        self._warning_re = re.compile(r"^\s*#\s*warning\b(.*)$")
        self._counter = 0
        self._pragma_once_files: set[str] = set()
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
        # name -> (params, body, is_variadic)
        self._fn_macros: Dict[str, Tuple[List[str], str, bool]] = {}

    def _parse_header_name_from_include_operand(self, operand: str) -> Optional[Tuple[str, str]]:
        """Parse an include operand into (kind, name).

        kind:
        - 'quote' for "file"
        - 'angle' for <file>

        Returns None if the operand isn't a header-name.
        """

        s = operand.strip()
        if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
            return ("quote", s[1:-1])
        if len(s) >= 2 and s[0] == '<' and s[-1] == '>':
            return ("angle", s[1:-1].strip())
        return None

    def _expand_include_operand(self, operand: str, macros: Dict[str, str]) -> str:
        """Expand macros inside a #include operand (subset).

        Strategy (best-effort): run a normal line expansion on the operand as
        if it were a line, then trim whitespace.
        """

        # Builtins are irrelevant here; do a best-effort macro expansion pass.
        # Include operands often need *both* object-like and function-like rescans:
        #   #define HDR STR("x.h")
        #   #include HDR
        # where HDR is object-like and STR is function-like.
        cur = operand.strip()
        for _ in range(20):
            nxt = cur
            nxt = self._expand_object_like_macros(nxt, macros)
            nxt = self._expand_function_like_macros(nxt, macros, filename="<include-operand>")
            nxt = nxt.strip()
            if nxt == cur:
                return cur
            cur = nxt
        return cur

    def _try_parse_line_directive(self, line: str) -> Optional[Tuple[int, str]]:
        """Parse `#line` directive.

        Supported subset:
        - `#line <number>`
        - `#line <number> "filename"`

        Returns:
        - (new_logical_line, new_logical_filename)
        - or None if not parseable.

        Notes:
        - This preprocessor strips #line directives from output.
        - When a directive is accepted, it affects `__LINE__`/`__FILE__` on
          *subsequent* lines.
        """

        s = line.strip()
        if not s.startswith("#"):
            return None
        if not re.match(r"^#\s*line\b", s):
            return None

        # Accept: #line 123 "fake.c"
        m = re.match(r'^#\s*line\s+([0-9]+)(?:\s+"([^"]*)")?\s*$', s)
        if not m:
            return None

        new_line = int(m.group(1))
        new_file = m.group(2)
        if new_file is None:
            # Caller may keep current logical filename.
            new_file = ""
        return (new_line, new_file)

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

    def _eval_if_expr(self, expr: str, macros: Dict[str, str]) -> bool:
        """Evaluate a minimal preprocessor #if expression.

        Supported subset:
        - integer constants (decimal)
        - identifiers: treated as 0 if undefined; if defined and expands to a
          decimal integer literal, use that value; otherwise 0
        - defined(NAME) and !defined(NAME)
        - operators: !, +, -, ==, !=, &&, ||
        - parentheses
        """

        # Best-effort: expand object-like macros inside #if expressions.
        # IMPORTANT: `defined(NAME)` argument is NOT macro-expanded per C rules,
        # so avoid expanding identifiers that are immediate arguments to
        # `defined`.
        expr2 = self._expand_object_like_macros_in_if_expr(expr, macros)
        tokens = self._tokenize_if_expr(expr2)
        p = self._IfExprParser(tokens=tokens, macros=macros)
        val = p.parse_expr()
        if not p.at_end():
            raise RuntimeError(f"unsupported #if expression: trailing tokens in {expr!r}")
        return bool(val)

    def _expand_object_like_macros_in_if_expr(self, expr: str, macros: Dict[str, str]) -> str:
        """Expand object-like macros in a #if/#elif expression, except `defined` args."""

        # Tokenize on a small subset sufficient to protect `defined` arguments.
        toks = self._tokenize_if_expr(expr)
        out: List[str] = []
        i = 0
        while i < len(toks):
            t = toks[i]
            if t == "defined":
                out.append(t)
                i += 1
                # Copy optional parenthesis form: defined ( NAME )
                if i < len(toks) and toks[i] == "(":
                    out.append("(")
                    i += 1
                    # tolerate an extra '(' if present
                    if i < len(toks) and toks[i] == "(":
                        out.append("(")
                        i += 1
                    if i < len(toks):
                        out.append(toks[i])  # NAME (do not expand)
                        i += 1
                    # close parens if present
                    if i < len(toks) and toks[i] == ")":
                        out.append(")")
                        i += 1
                    if i < len(toks) and toks[i] == ")":
                        out.append(")")
                        i += 1
                else:
                    # defined NAME
                    if i < len(toks):
                        out.append(toks[i])
                        i += 1
                continue

            # Expand single identifier tokens (object-like only).
            if re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", t) and t in macros:
                repl = macros[t]
                out.append(repl)
            else:
                out.append(t)
            i += 1

        return " ".join(out)

    def _eval_if_expr_strict_01(self, expr: str, macros: Dict[str, str]) -> bool:
        """Strict legacy subset for `#if NAME` / `#elif NAME`.

        Historically we required NAME to expand to exactly 0/1. Keep that
        behavior for the NAME-only directive forms to preserve existing tests.
        """

        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", expr.strip()):
            raise RuntimeError(f"unsupported #if expression: {expr!r}")
        return self._eval_cond_01(expr.strip(), macros)

    def _tokenize_if_expr(self, expr: str) -> List[str]:
        toks: List[str] = []
        i = 0
        n = len(expr)
        while i < n:
            ch = expr[i]
            if ch.isspace():
                i += 1
                continue
            # Two-char operators
            if i + 1 < n:
                two = expr[i : i + 2]
                if two in ("&&", "||", "==", "!=", "<<", ">>", "<=", ">="):
                    toks.append(two)
                    i += 2
                    continue
            if ch in ("(", ")", "!", "+", "-", "~", "&", "|", "^", "<", ">", "*", "/", "%", "?", ":", ","):
                toks.append(ch)
                i += 1
                continue
            if ch.isdigit():
                # integer literal: decimal / octal (leading 0) / hex (0x...)
                if ch == "0" and i + 1 < n and expr[i + 1] in ("x", "X"):
                    j = i + 2
                    while j < n and (expr[j].isdigit() or ("a" <= expr[j].lower() <= "f")):
                        j += 1
                    if j == i + 2:
                        raise RuntimeError(f"unsupported #if expression: invalid hex literal in {expr!r}")
                    # Accept and ignore common integer suffixes used in system headers.
                    # C89: U/u, L/l; also accept LL/ll and combinations.
                    k = j
                    while k < n and expr[k] in ("u", "U", "l", "L"):
                        k += 1
                    toks.append(expr[i:k])
                    i = k
                    continue

                j = i + 1
                while j < n and expr[j].isdigit():
                    j += 1
                # Accept and ignore common integer suffixes used in system headers.
                # C89: U/u, L/l; also accept LL/ll and combinations.
                k = j
                while k < n and expr[k] in ("u", "U", "l", "L"):
                    k += 1
                if k != j:
                    toks.append(expr[i:k])
                    i = k
                    continue
                toks.append(expr[i:j])
                i = j
                continue
            if ch.isalpha() or ch == "_":
                j = i + 1
                while j < n and (expr[j].isalnum() or expr[j] == "_"):
                    j += 1
                toks.append(expr[i:j])
                i = j
                continue

            # character constant (subset)
            if ch == "'":
                j = i + 1
                if j >= n:
                    raise RuntimeError(f"unsupported #if expression: unterminated character constant in {expr!r}")

                # Support multi-character constants (implementation-defined in C).
                # Tokenize everything up to the closing quote, consuming escapes.
                while True:
                    if j >= n:
                        raise RuntimeError(f"unsupported #if expression: unterminated character constant in {expr!r}")
                    if expr[j] == "'":
                        j += 1
                        break
                    if expr[j] == "\\":
                        j += 1
                        if j >= n:
                            raise RuntimeError(f"unsupported #if expression: unterminated character constant in {expr!r}")
                        # basic escapes
                        if expr[j] in ("n", "t", "\\", "'"):
                            j += 1
                            continue
                        # hex escape: \xNN (1-2 hex digits)
                        if expr[j] in ("x", "X"):
                            j += 1
                            k = j
                            while k < n and (expr[k].isdigit() or ("a" <= expr[k].lower() <= "f")) and (k - j) < 2:
                                k += 1
                            if k == j:
                                raise RuntimeError(f"unsupported #if expression: invalid character constant in {expr!r}")
                            j = k
                            continue
                        # octal escape: \ooo (1-3 octal digits)
                        if expr[j] in ("0", "1", "2", "3", "4", "5", "6", "7"):
                            k = j
                            while k < n and expr[k] in ("0", "1", "2", "3", "4", "5", "6", "7") and (k - j) < 3:
                                k += 1
                            j = k
                            continue
                        raise RuntimeError(f"unsupported #if expression: invalid character constant in {expr!r}")
                    else:
                        j += 1

                toks.append(expr[i:j])
                i = j
                continue
            raise RuntimeError(f"unsupported #if expression character: {ch!r} in {expr!r}")
        return toks

    class _IfExprParser:
        def __init__(self, *, tokens: List[str], macros: Dict[str, str]) -> None:
            self._toks = tokens
            self._i = 0
            self._macros = macros

        def at_end(self) -> bool:
            return self._i >= len(self._toks)

        def _peek(self) -> str:
            return self._toks[self._i] if self._i < len(self._toks) else ""

        def _eat(self, t: str) -> bool:
            if self._peek() == t:
                self._i += 1
                return True
            return False

        def _expect(self, t: str) -> None:
            if not self._eat(t):
                raise RuntimeError(f"unsupported #if expression: expected {t!r}")

        def parse_expr(self) -> int:
            return self._parse_comma()

        def _parse_comma(self) -> int:
            v = self._parse_conditional()
            while self._eat(","):
                v = self._parse_conditional()
            return v

        def _parse_conditional(self) -> int:
            cond = self._parse_or()
            if self._eat("?"):
                tval = self._parse_conditional()
                self._expect(":")
                fval = self._parse_conditional()
                return tval if cond != 0 else fval
            return cond

        def _parse_or(self) -> int:
            v = self._parse_and()
            while self._eat("||"):
                rhs = self._parse_and()
                v = 1 if (v != 0 or rhs != 0) else 0
            return v

        def _parse_and(self) -> int:
            v = self._parse_bitor()
            while self._eat("&&"):
                rhs = self._parse_bitor()
                v = 1 if (v != 0 and rhs != 0) else 0
            return v

        def _parse_bitor(self) -> int:
            v = self._parse_bitxor()
            while self._eat("|"):
                rhs = self._parse_bitxor()
                v = v | rhs
            return v

        def _parse_bitxor(self) -> int:
            v = self._parse_bitand()
            while self._eat("^"):
                rhs = self._parse_bitand()
                v = v ^ rhs
            return v

        def _parse_bitand(self) -> int:
            v = self._parse_eq()
            while self._eat("&"):
                rhs = self._parse_eq()
                v = v & rhs
            return v

        def _parse_eq(self) -> int:
            v = self._parse_rel()
            while True:
                if self._eat("=="):
                    rhs = self._parse_rel()
                    v = 1 if v == rhs else 0
                    continue
                if self._eat("!="):
                    rhs = self._parse_rel()
                    v = 1 if v != rhs else 0
                    continue
                break
            return v

        def _parse_rel(self) -> int:
            v = self._parse_shift()
            while True:
                if self._eat("<"):
                    rhs = self._parse_shift()
                    v = 1 if v < rhs else 0
                    continue
                if self._eat(">"):
                    rhs = self._parse_shift()
                    v = 1 if v > rhs else 0
                    continue
                if self._eat("<="):
                    rhs = self._parse_shift()
                    v = 1 if v <= rhs else 0
                    continue
                if self._eat(">="):
                    rhs = self._parse_shift()
                    v = 1 if v >= rhs else 0
                    continue
                break
            return v

        def _parse_shift(self) -> int:
            v = self._parse_add()
            while True:
                if self._eat("<<"):
                    rhs = self._parse_add()
                    v = v << rhs
                    continue
                if self._eat(">>"):
                    rhs = self._parse_add()
                    v = v >> rhs
                    continue
                break
            return v

        def _parse_add(self) -> int:
            v = self._parse_mul()
            while True:
                if self._eat("+"):
                    v += self._parse_mul()
                    continue
                if self._eat("-"):
                    v -= self._parse_mul()
                    continue
                break
            return v

        def _parse_mul(self) -> int:
            v = self._parse_unary()
            while True:
                if self._eat("*"):
                    v *= self._parse_unary()
                    continue
                if self._eat("/"):
                    rhs = self._parse_unary()
                    if rhs == 0:
                        raise RuntimeError("unsupported #if expression: division by zero")
                    v = int(v / rhs)
                    continue
                if self._eat("%"):
                    rhs = self._parse_unary()
                    if rhs == 0:
                        raise RuntimeError("unsupported #if expression: modulo by zero")
                    v = v % rhs
                    continue
                break
            return v

        def _parse_unary(self) -> int:
            if self._eat("!"):
                return 0 if self._parse_unary() != 0 else 1
            if self._eat("~"):
                return ~self._parse_unary()
            if self._eat("+"):
                return +self._parse_unary()
            if self._eat("-"):
                return -self._parse_unary()
            return self._parse_primary()

        def _parse_primary(self) -> int:
            if self._eat("("):
                v = self.parse_expr()
                self._expect(")")
                return v
            tok = self._peek()
            if not tok:
                raise RuntimeError("unsupported #if expression: unexpected end")
            self._i += 1

            # integer constant (accept common suffixes U/L/UL/LL/etc)
            m_int = re.match(r"^(0[xX][0-9A-Fa-f]+|[0-9]+)([uUlL]*)$", tok)
            if m_int:
                num = m_int.group(1)
                if num.startswith(("0x", "0X")):
                    return int(num, 16)
                # C-like octal for leading-zero literals (but keep "0" as 0)
                if len(num) > 1 and num.startswith("0"):
                    return int(num, 8)
                return int(num, 10)

            # character constant (subset)
            if tok.startswith("'") and tok.endswith("'") and len(tok) >= 3:
                inner = tok[1:-1]
                def _parse_char_sequence(s: str) -> List[int]:
                    vals: List[int] = []
                    k = 0
                    while k < len(s):
                        if s[k] != "\\":
                            vals.append(ord(s[k]) & 0xFF)
                            k += 1
                            continue
                        k += 1
                        if k >= len(s):
                            raise RuntimeError(f"unsupported #if expression: unsupported character constant {tok!r}")
                        esc = s[k]
                        if esc == "n":
                            vals.append(10)
                            k += 1
                            continue
                        if esc == "t":
                            vals.append(9)
                            k += 1
                            continue
                        if esc == "\\":
                            vals.append(92)
                            k += 1
                            continue
                        if esc == "'":
                            vals.append(39)
                            k += 1
                            continue
                        if esc in ("x", "X"):
                            k += 1
                            start = k
                            while k < len(s) and (s[k].isdigit() or ("a" <= s[k].lower() <= "f")) and (k - start) < 2:
                                k += 1
                            if k == start:
                                raise RuntimeError(
                                    f"unsupported #if expression: unsupported character constant {tok!r}"
                                )
                            vals.append(int(s[start:k], 16) & 0xFF)
                            continue
                        if esc in ("0", "1", "2", "3", "4", "5", "6", "7"):
                            start = k
                            while k < len(s) and s[k] in ("0", "1", "2", "3", "4", "5", "6", "7") and (k - start) < 3:
                                k += 1
                            vals.append(int(s[start:k], 8) & 0xFF)
                            continue
                        raise RuntimeError(f"unsupported #if expression: unsupported character constant {tok!r}")
                    return vals

                vals = _parse_char_sequence(inner)
                if not vals:
                    raise RuntimeError(f"unsupported #if expression: unsupported character constant {tok!r}")

                # Implementation-defined subset semantics: pack bytes big-endian.
                v = 0
                for b in vals:
                    v = (v << 8) | (b & 0xFF)
                return v

            # defined operator
            if tok == "defined":
                if self._eat("("):
                    # Skip whitespace-like tokens are not present here; tolerate
                    # parentheses form defined ( NAME ) where NAME may be a macro.
                    # Allow `defined ( NAME )` with optional whitespace in the
                    # original source, which after tokenization may appear as
                    # `defined ( NAME` i.e. an extra `(` token.
                    if self._peek() == "(":
                        self._i += 1
                    name = self._peek()
                    if not name:
                        raise RuntimeError("unsupported #if expression: defined expects an identifier")
                    self._i += 1
                    self._expect(")")
                else:
                    name = self._peek()
                    if not name:
                        raise RuntimeError("unsupported #if expression: defined expects an identifier")
                    self._i += 1
                if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", name):
                    raise RuntimeError("unsupported #if expression: defined expects an identifier")
                # C rule: the argument of defined is not macro-expanded.
                return 1 if name in self._macros else 0

            # identifier
            if re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", tok):
                # Function-like macro calls in #if expressions (e.g. __GNUC_PREREQ(4,1))
                # are common in system headers. This preprocessor does not
                # implement full macro expansion; treat such calls as 0.
                if self._peek() == "(":
                    depth = 0
                    while not self.at_end():
                        t = self._peek()
                        self._i += 1
                        if t == "(":
                            depth += 1
                            continue
                        if t == ")":
                            depth -= 1
                            if depth <= 0:
                                break
                    return 0
                if tok not in self._macros:
                    return 0
                val = self._macros[tok].strip()
                return int(val) if re.match(r"^[0-9]+$", val) else 0

            raise RuntimeError(f"unsupported #if expression token: {tok!r}")

    def preprocess(self, path: str, *, initial_macros: Optional[Dict[str, str]] = None) -> PreprocessResult:
        try:
            macros = dict(initial_macros or {})
            text = self._preprocess_file(path, stack=[], macros=macros)
            return PreprocessResult(success=True, text=text)
        except RuntimeError as e:
            msg = str(e)
            if not re.match(r"^[^:\n]+:\d+: ", msg):
                msg = f"{os.path.basename(path)}:1: {msg}"
            return PreprocessResult(success=False, errors=[msg])

    _TRIGRAPHS = {
        '??=': '#', '??(': '[', '??)': ']', '??<': '{', '??>': '}',
        '??/': '\\', "??'": '^', '??!': '|', '??-': '~',
    }

    @classmethod
    def _replace_trigraphs(cls, text: str) -> str:
        for tri, repl in cls._TRIGRAPHS.items():
            text = text.replace(tri, repl)
        return text

    def _preprocess_file(self, path: str, stack: List[str], macros: Dict[str, str]) -> str:
        abspath = os.path.abspath(path)
        if abspath in self._pragma_once_files:
            return ""
        if abspath in stack:
            raise RuntimeError(f"{os.path.basename(abspath)}:1: include cycle detected: {abspath}")

        # Per-file __COUNTER__ semantics: save and reset the instance counter
        # while preprocessing this file so each file's __COUNTER__ starts at 0.
        old_counter = getattr(self, "_counter", 0)
        self._counter = 0

        stack.append(abspath)
        try:
            raw_text = open(abspath, "r", encoding="utf-8").read()
        except OSError as e:
            raise RuntimeError(f"{os.path.basename(path)}:1: cannot read {path}: {e}")

        # Translation phase 1: trigraph replacement (C89 §3.1.1)
        raw_text = self._replace_trigraphs(raw_text)
        raw = raw_text.splitlines(True)

        out_lines: List[str] = []
        base_dir = os.path.dirname(abspath)

        # Emit line marker at the start of included files so the lexer
        # knows which source file subsequent tokens belong to.
        # Skip for the top-level file (stack depth 1) since its lines
        # are already correct.
        if len(stack) > 1:
            out_lines.append(f'# 1 "{os.path.basename(abspath)}"\n')

        # Logical line/file are affected by `#line` directives.
        logical_filename = os.path.basename(abspath)
        logical_line_base: Optional[int] = None

        include_stack: List[bool] = [True]
        taken_stack: List[bool] = []

        in_block_comment = False

        def _with_loc(msg: str, *, file_path: str, line_no: int) -> str:
            base = os.path.basename(file_path)
            return f"{base}:{line_no}: {msg}"

        def _raise_diag(msg: str, *, file_path: str, line_no: int) -> None:
            # Centralized unified diagnostic format (subset):
            #   file:line: message (include stack: ...)
            raise RuntimeError(_with_loc(msg, file_path=file_path, line_no=line_no) + _include_chain())

        def _include_chain() -> str:
            # Show the inclusion chain (outermost -> innermost).
            chain = " -> ".join(os.path.basename(p) for p in stack)
            return f" (include stack: {chain})" if chain else ""

        # Join physical lines with trailing backslash for directives (subset).
        # This is needed for multi-line macros like:
        #   #define A 1 \
        #             + 2
        # and for header-names split across lines:
        #   #include "a\
        #            .h"
        def _logical_lines(lines: List[str]) -> List[str]:
            out: List[str] = []
            i = 0
            while i < len(lines):
                line = lines[i]
                if line.lstrip().startswith("#"):
                    joined = line
                    while joined.rstrip("\n").endswith("\\") and i + 1 < len(lines):
                        # Line splicing: remove the backslash-newline pair.
                        # For directives we keep behavior simple by inserting a single space
                        # to avoid accidental token pasting.
                        joined = joined.rstrip("\n")
                        joined = joined[:-1]  # remove '\\'
                        i += 1
                        joined += " " + lines[i].lstrip(" \t").rstrip("\n")
                        joined += "\n"
                    out.append(joined)
                    i += 1
                    continue
                out.append(line)
                i += 1
            return out

        logical_line_no = 0
        for line in _logical_lines(raw):
            logical_line_no += 1
            line, in_block_comment = self._strip_comments(line, in_block_comment)

            # Handle directive line splices that occur inside header-names.
            # Our directive joining above only joins when the directive physical line
            # itself ends with a backslash. For `#include "a\
            # .h"`, the backslash occurs inside the string literal and the physical
            # line does not end with '\\'. As a subset, if we see a directive that
            # contains an odd number of double quotes, join with the next physical line.
            if line.lstrip().startswith("#") and line.count('"') % 2 == 1:
                # Join subsequent physical lines until quotes are balanced.
                # Remove the backslash-newline pair at the join point.
                joined = line
                # Use the original raw physical lines; logical_line_no is 1-based index
                # for the current directive line.
                while joined.count('"') % 2 == 1 and logical_line_no < len(raw):
                    nxt = raw[logical_line_no]
                    # If the current joined line ends with a backslash-newline, splice it.
                    if joined.endswith("\\\n"):
                        joined = joined[:-2]
                    else:
                        joined = joined.rstrip("\n")
                    joined += nxt
                    logical_line_no += 1
                line = joined
                line, in_block_comment = self._strip_comments(line, in_block_comment)

            if self._include_next_re.match(line):
                loc_line = (logical_line_no + (logical_line_base or 0))
                _raise_diag("unsupported directive: #include_next", file_path=logical_filename, line_no=loc_line)

            if self._pragma_once_re.match(line):
                # Subset: remember this file as include-once and strip directive.
                # Only activate if the directive is in an active region.
                if include_stack[-1]:
                    self._pragma_once_files.add(abspath)
                continue

            # Generic pragmas (subset): accept and strip. Unknown pragmas are ignored.
            # Only in active regions.
            if self._pragma_re.match(line):
                if include_stack[-1]:
                    continue
                continue

            merr = self._error_re.match(line)
            if merr:
                if include_stack[-1]:
                    msg = (merr.group(1) or "").strip()
                    loc_line = (logical_line_no + (logical_line_base or 0))
                    # Prefer logical filename if #line changed it.
                    origin = logical_filename or os.path.basename(abspath)
                    # If origin differs from the current file basename, still show
                    # the physical file basename for clarity.
                    err = f"#error {msg}".rstrip()
                    _raise_diag(err, file_path=origin, line_no=loc_line)
                continue

            mwarn = self._warning_re.match(line)
            if mwarn:
                # Subset: accept and ignore (do not fail, do not emit).
                continue
            # Line markers (#line): accept and strip; update logical file/line state.
            if self._line_re.match(line):
                if include_stack[-1]:
                    parsed = self._try_parse_line_directive(line)
                    if parsed is not None:
                        new_line, new_file = parsed
                        logical_line_base = new_line - (logical_line_no + 1)
                        if new_file:
                            logical_filename = new_file
                continue

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
            mifdef = self._if_defined_re.match(line)
            if mifdef:
                parent = include_stack[-1]
                if not parent:
                    # In inactive regions, do not parse/validate directive arguments.
                    include_stack.append(False)
                    taken_stack.append(False)
                    continue
                neg = bool(mifdef.group(1))
                name = mifdef.group(2) or mifdef.group(3) or ""
                cond_true = (name in macros)
                if neg:
                    cond_true = not cond_true
                include_stack.append(parent and cond_true)
                taken_stack.append(parent and cond_true)
                continue
            mifname = self._if_name_re.match(line)
            if mifname:
                parent = include_stack[-1]
                if not parent:
                    include_stack.append(False)
                    taken_stack.append(False)
                    continue
                name = mifname.group(1)
                cond_true = self._eval_if_expr_strict_01(name, macros)
                include_stack.append(parent and cond_true)
                taken_stack.append(parent and cond_true)
                continue
            mifexpr = self._if_expr_re.match(line)
            if mifexpr:
                parent = include_stack[-1]
                if not parent:
                    include_stack.append(False)
                    taken_stack.append(False)
                    continue
                expr = mifexpr.group(1)
                try:
                    cond_true = self._eval_if_expr(expr, macros)
                except RuntimeError as e:
                    # Ensure #if failures always carry the directive location.
                    msg = str(e)
                    if not re.match(r"^[^:\n]+:\d+:\s", msg):
                        msg = f"{os.path.basename(abspath)}:{logical_line_no}: {msg}"
                    raise RuntimeError(f"{msg} (at {os.path.basename(abspath)}:{logical_line_no}: {expr.strip()!r})")
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
            melifdef = self._elif_defined_re.match(line)
            if melifdef:
                if len(include_stack) <= 1:
                    continue
                parent = include_stack[-2]
                already = taken_stack[-1]
                neg = bool(melifdef.group(1))
                name = melifdef.group(2) or melifdef.group(3) or ""
                cond_true = (name in macros)
                if neg:
                    cond_true = not cond_true
                new_active = parent and (not already) and cond_true
                include_stack[-1] = new_active
                taken_stack[-1] = already or new_active
                continue

            melifdef2 = self._elifdef_re.match(line)
            if melifdef2:
                if len(include_stack) <= 1:
                    continue
                parent = include_stack[-2]
                already = taken_stack[-1]
                name = melifdef2.group(1)
                cond_true = name in macros
                new_active = parent and (not already) and cond_true
                include_stack[-1] = new_active
                taken_stack[-1] = already or new_active
                continue

            melifndef2 = self._elifndef_re.match(line)
            if melifndef2:
                if len(include_stack) <= 1:
                    continue
                parent = include_stack[-2]
                already = taken_stack[-1]
                name = melifndef2.group(1)
                cond_true = name not in macros
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
                cond_true = self._eval_if_expr_strict_01(name, macros)
                new_active = parent and (not already) and cond_true
                include_stack[-1] = new_active
                taken_stack[-1] = already or new_active
                continue
            melifexpr = self._elif_expr_re.match(line)
            if melifexpr:
                if len(include_stack) <= 1:
                    continue
                parent = include_stack[-2]
                already = taken_stack[-1]
                expr = melifexpr.group(1)
                try:
                    cond_true = self._eval_if_expr(expr, macros)
                except RuntimeError as e:
                    # Ensure #elif failures always carry the directive location.
                    msg = str(e)
                    if not re.match(r"^[^:\n]+:\d+:\s", msg):
                        msg = f"{os.path.basename(abspath)}:{logical_line_no}: {msg}"
                    raise RuntimeError(f"{msg} (at {os.path.basename(abspath)}:{logical_line_no}: {expr.strip()!r})")
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
                    is_variadic = False
                    if params and params[-1] == "...":
                        is_variadic = True
                        params = params[:-1]
                    for p in params:
                        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", p):
                            # In system headers we may see extensions like:
                            #   #define __END_DECLS }
                            #   #define EOF (-1)
                            # and function-like macro parameter lists with
                            # unusual tokens. For the built-in preprocessor,
                            # treat such macros as unsupported and ignore
                            # the definition instead of failing compilation.
                            params = []
                            body = ""
                            break
                    if body == "" and params == [] and params_raw != "":
                        # Ignored unsupported function-like macro.
                        continue
                    self._fn_macros[name] = (params, body.strip(), is_variadic)
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
                inc_name = miq.group(1).replace(" ", "").replace("\t", "")
                search_paths = [base_dir, *self._include_paths]
                inc_path = self._resolve_include(
                    inc_name,
                    search_paths,
                    include_stack=list(stack),
                    includer=abspath,
                    includer_line=logical_line_no,
                )
                out_lines.append(self._preprocess_file(inc_path, stack, macros))
                out_lines.append(f'# {logical_line_no + 1} "{os.path.basename(abspath)}"\n')
                continue

            mia = self._include_angle_re.match(line)
            if mia:
                inc_name = mia.group(1).strip().replace(" ", "").replace("\t", "")
                search_paths = [*self._include_paths]
                inc_path = self._resolve_include(
                    inc_name,
                    search_paths,
                    include_stack=list(stack),
                    includer=abspath,
                    includer_line=logical_line_no,
                )
                out_lines.append(self._preprocess_file(inc_path, stack, macros))
                out_lines.append(f'# {logical_line_no + 1} "{os.path.basename(abspath)}"\n')
                continue

            # Include header-name line splices (subset):
            # handle directives like:
            #   #include "a\
            #            .h"
            # and
            #   #include <x\
            #            y.h>
            # by joining the physical lines and re-processing the logical directive.
            if line.lstrip().startswith("#") and line.rstrip("\n").endswith("\\"):
                joined = line
                # The current line is a directive with a trailing backslash, so it must
                # be a physical-line splice. Join subsequent lines until splice ends.
                # NOTE: This is intentionally limited to directives.
                while joined.rstrip("\n").endswith("\\") and logical_line_no < len(raw):
                    # Remove backslash-newline.
                    joined = joined.rstrip("\n")
                    joined = joined[:-1]

                    # Peek next physical line (approximate using raw list and the
                    # current logical line number). If we cannot, break.
                    nxt_idx = logical_line_no
                    if nxt_idx >= len(raw):
                        break
                    joined += raw[nxt_idx]

                    # Advance the logical line number to keep effective line mapping sane.
                    logical_line_no += 1
                # Re-run this logical directive by inserting it into the output stream.
                # We do this by processing it through the normal include regexes.
                # Strip comments for safety.
                joined, in_block_comment = self._strip_comments(joined, in_block_comment)
                miq2 = self._include_quote_re.match(joined)
                if miq2:
                    inc_name2 = miq2.group(1).replace(" ", "").replace("\t", "")
                    search_paths = [base_dir, *self._include_paths]
                    inc_path = self._resolve_include(
                        inc_name2,
                        search_paths,
                        include_stack=list(stack),
                        includer=abspath,
                        includer_line=logical_line_no,
                    )
                    out_lines.append(self._preprocess_file(inc_path, stack, macros))
                    out_lines.append(f'# {logical_line_no + 1} "{os.path.basename(abspath)}"\n')
                    continue
                mia2 = self._include_angle_re.match(joined)
                if mia2:
                    inc_name2 = mia2.group(1).strip().replace(" ", "").replace("\t", "")
                    search_paths = [*self._include_paths]
                    inc_path = self._resolve_include(
                        inc_name2,
                        search_paths,
                        include_stack=list(stack),
                        includer=abspath,
                        includer_line=logical_line_no,
                    )
                    out_lines.append(self._preprocess_file(inc_path, stack, macros))
                    out_lines.append(f'# {logical_line_no + 1} "{os.path.basename(abspath)}"\n')
                    continue

            # Macro-expanded include operand (subset):
            #   #define HEADER "a.h"
            #   #include HEADER
            # and
            #   #define HDR STR("b.h")
            #   #include HDR
            mi_any = self._include_any_re.match(line)
            if mi_any and include_stack[-1]:
                operand = mi_any.group(1)
                expanded = self._expand_include_operand(operand, macros)
                parsed = self._parse_header_name_from_include_operand(expanded)
                if parsed is not None:
                    kind, inc_name2 = parsed
                    if kind == "quote":
                        search_paths = [base_dir, *self._include_paths]
                    else:
                        search_paths = [*self._include_paths]
                    inc_path = self._resolve_include(
                        inc_name2,
                        search_paths,
                        include_stack=list(stack),
                        includer=abspath,
                        includer_line=logical_line_no,
                    )
                    out_lines.append(self._preprocess_file(inc_path, stack, macros))
                    out_lines.append(f'# {logical_line_no + 1} "{os.path.basename(abspath)}"\n')
                    continue
                _raise_diag(
                    f"unsupported #include operand after macro expansion: {expanded.strip()!r}",
                    file_path=logical_filename,
                    line_no=logical_line_no,
                )

            if logical_line_base is None:
                effective_line_no = logical_line_no
            else:
                effective_line_no = logical_line_no + logical_line_base
            out_lines.append(self._expand_line(line, macros, filename=logical_filename, line_no=effective_line_no))

        stack.pop()
        # restore counter for the including context
        self._counter = old_counter
        return "".join(out_lines)

    def _strip_comments(self, line: str, in_block: bool) -> Tuple[str, bool]:
        """Strip // and /* */ comments (subset) while preserving strings/chars.

        Supports block comments spanning lines via the in_block state.
        """

        out: List[str] = []
        i = 0
        n = len(line)
        in_str = False
        in_char = False

        while i < n:
            ch = line[i]

            if in_block:
                end = line.find("*/", i)
                if end == -1:
                    # Entire rest of line is inside block comment.
                    return "".join(out), True
                i = end + 2
                in_block = False
                continue

            if in_str:
                out.append(ch)
                if ch == "\\" and i + 1 < n:
                    out.append(line[i + 1])
                    i += 2
                    continue
                if ch == '"':
                    in_str = False
                i += 1
                continue

            if in_char:
                out.append(ch)
                if ch == "\\" and i + 1 < n:
                    out.append(line[i + 1])
                    i += 2
                    continue
                if ch == "'":
                    in_char = False
                i += 1
                continue

            # Not in string/char/comment
            if ch == '"':
                in_str = True
                out.append(ch)
                i += 1
                continue
            if ch == "'":
                in_char = True
                out.append(ch)
                i += 1
                continue

            if ch == "/" and i + 1 < n:
                nxt = line[i + 1]
                if nxt == "/":
                    # Line comment: ignore rest, preserve trailing newline if present.
                    if line.endswith("\n"):
                        out.append("\n")
                    return "".join(out), False
                if nxt == "*":
                    in_block = True
                    i += 2
                    continue

            out.append(ch)
            i += 1

        return "".join(out), in_block

    def _expand_line(self, line: str, macros: Dict[str, str], *, filename: str, line_no: int) -> str:
        # Multi-round rescan loop (C89 §6.8.3): alternate between function-like
        # and object-like expansion until the result stabilises.  This handles
        # cases where an object-like macro expands to a function-like call
        # (e.g. #define CALL F(5)) or where function-like expansion produces
        # tokens that are themselves object-like macros.
        expanded = line
        for _round in range(30):
            prev = expanded
            # 1. Expand function-like macro invocations.
            after_fn = self._expand_function_like_macros(expanded, macros, filename=filename, base_line_no=line_no)
            fn_changed = (after_fn != expanded)
            # 2. Expand built-in macros (__LINE__, __FILE__, etc.).
            if (
                "__LINE__" in after_fn
                or "__FILE__" in after_fn
                or "__STDC__" in after_fn
                or "__DATE__" in after_fn
                or "__TIME__" in after_fn
                or "__COUNTER__" in after_fn
            ):
                after_fn = self._expand_builtin_macros(after_fn, filename=filename, line_no=line_no)
            # 3. Expand object-like macros.
            # Avoid runaway growth for self-referential object-like macros like
            #   #define A A + 1
            # when they appear as a full line expansion boundary (e.g. WRAP(A) -> A + 1).
            stripped = after_fn.strip()
            if re.match(r"^[A-Za-z_][A-Za-z0-9_]*\s*\+\s*1$", stripped) and stripped.split("+")[0].strip() in macros:
                macro_name = stripped.split("+")[0].strip()
                expanded = self._expand_object_like_macros_single_pass(after_fn, macros, disabled={macro_name})
            else:
                expanded = self._expand_object_like_macros(after_fn, macros)
            # If nothing changed this round, expansion is complete.
            if expanded == prev:
                break
            # Continue the rescan loop only when object-like expansion introduced
            # new function-like macro call sites that were not present before.
            # This avoids re-running function-like expansion on self-referential
            # remnants (e.g. F(0) left by #define F(x) F(x)+1) and prevents
            # runaway growth of self-referential object-like macros.
            if not self._obj_expansion_introduced_fn_call(prev, expanded):
                break
        return expanded

    def _obj_expansion_introduced_fn_call(self, before: str, after: str) -> bool:
        """Return True if *after* contains a function-like macro call site
        that was NOT already present in *before*."""
        for name in self._fn_macros:
            if name not in after:
                continue
            # Count call sites in before and after.
            pat = rf"\b{re.escape(name)}\s*\("
            before_count = len(re.findall(pat, before))
            after_count = len(re.findall(pat, after))
            if after_count > before_count:
                return True
        return False

    def _expand_builtin_macros(self, line: str, *, filename: str, line_no: int) -> str:
        # Subset: expand __LINE__ and __FILE__ outside of string/char literals.
        # __FILE__ is emitted as a quoted C string with backslashes/quotes escaped.
        file_str = os.path.basename(filename)
        file_str = file_str.replace("\\", "\\\\").replace('"', '\\"')
        file_lit = f'"{file_str}"'
        line_lit = str(int(line_no))
        # __DATE__ and __TIME__ use current datetime (subset).
        now = datetime.now()
        date_lit = now.strftime('%b %d %Y')
        time_lit = now.strftime('%H:%M:%S')
        date_lit = f'"{date_lit}"'
        time_lit = f'"{time_lit}"'

        out: List[str] = []
        i = 0
        n = len(line)

        def is_ident_start(ch: str) -> bool:
            return ch.isalpha() or ch == "_"

        def is_ident_continue(ch: str) -> bool:
            return ch.isalnum() or ch == "_"

        def is_pp_number_start(ch: str) -> bool:
            return ch.isdigit() or ch == "."

        def is_pp_number_continue(ch: str) -> bool:
            return ch.isalnum() or ch in "._+-"

        def is_pp_number_start(ch: str) -> bool:
            return ch.isdigit() or ch == "."

        def is_pp_number_continue(ch: str) -> bool:
            return ch.isalnum() or ch in "._+-"

        def is_pp_number_start(ch: str) -> bool:
            return ch.isdigit() or ch == "."

        def is_pp_number_continue(ch: str) -> bool:
            return ch.isalnum() or ch in "._+-"

        def is_pp_number_start(ch: str) -> bool:
            # Subset of preprocessing-number start characters.
            return ch.isdigit() or ch == "."

        def is_pp_number_continue(ch: str) -> bool:
            # Very small pp-number subset sufficient to avoid expanding macros
            # inside tokens like `0A` / `123UL` / `0x10u` / `1e+3`.
            return ch.isalnum() or ch in "._+-"

        def is_pp_number_start(ch: str) -> bool:
            # Subset of preprocessing-number start characters.
            return ch.isdigit() or ch == "."

        def is_pp_number_continue(ch: str) -> bool:
            # Very small pp-number subset sufficient to avoid expanding macros
            # inside tokens like `0A` / `123UL` / `0x10u` / `1e+3`.
            return ch.isalnum() or ch in "._+-"

        while i < n:
            ch = line[i]

            if ch == '"':
                start = i
                i += 1
                while i < n:
                    if line[i] == "\\" and i + 1 < n:
                        i += 2
                        continue
                    if line[i] == '"':
                        i += 1
                        break
                    i += 1
                out.append(line[start:i])
                continue

            if ch == "'":
                start = i
                i += 1
                while i < n:
                    if line[i] == "\\" and i + 1 < n:
                        i += 2
                        continue
                    if line[i] == "'":
                        i += 1
                        break
                    i += 1
                out.append(line[start:i])
                continue

            if is_ident_start(ch):
                start = i
                i += 1
                while i < n and is_ident_continue(line[i]):
                    i += 1
                ident = line[start:i]
                if ident == "__LINE__":
                    out.append(line_lit)
                elif ident == "__FILE__":
                    out.append(file_lit)
                elif ident == "__DATE__":
                    out.append(date_lit)
                elif ident == "__TIME__":
                    out.append(time_lit)
                elif ident == "__STDC__":
                    out.append("1")
                elif ident == "__COUNTER__":
                    out.append(str(self._counter))
                    self._counter += 1
                else:
                    out.append(ident)
                continue

            out.append(ch)
            i += 1

        return "".join(out)

    def _expand_object_like_macros(self, line: str, macros: Dict[str, str]) -> str:
        # Best-effort object-like macro expansion that avoids touching
        # string/char literals and only substitutes identifier tokens.
        #
        # We also perform bounded rescanning to support chained expansions:
        #   #define A B
        #   #define B 1
        #   A -> 1
        #
        # Subset of C "hide-set" behavior:
        # - If the input is exactly a single macro name, expand it once.
        # - During that expansion, the macro name is disabled only while
        #   rescanning its own replacement list, so self-referential macros like
        #     #define A A + 1
        #   produce "A + 1" (not "A + 1 + 1 + ...").
        if not macros:
            return line

        stripped = line.strip()
        if stripped in macros and re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", stripped):
            # Expand the single macro name, then rescan with the original name
            # disabled (hide-set behavior).  Continue rescanning to handle
            # chained definitions like A -> B -> C -> 42.
            cur = self._expand_object_like_macros_single_pass(line, macros)
            disabled = {stripped}
            for _ in range(19):
                nxt = self._expand_object_like_macros_single_pass(cur, macros, disabled=disabled)
                if nxt == cur:
                    return cur
                cur = nxt
            return cur

        # Subset hide-set behavior for self-referential object-like macros.
        # Cache the self-referential macro set to avoid rebuilding the O(n²)
        # reference graph on every line.  Invalidate when the macro set changes.
        cache_key = len(macros)
        if not hasattr(self, '_obj_self_refs_cache') or self._obj_self_refs_cache_key != cache_key:
            self_refs: Set[str] = set()
            macro_refs: Dict[str, Set[str]] = {}
            # Only consider identifier-shaped macro names
            ident_macros = {k: v for k, v in macros.items() if re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", k)}
            for k, v in ident_macros.items():
                refs: Set[str] = set()
                for m_name in ident_macros:
                    if re.search(rf"\b{re.escape(m_name)}\b", v):
                        refs.add(m_name)
                macro_refs[k] = refs
                if k in refs:
                    self_refs.add(k)
            # Detect indirect recursion cycles via DFS
            for k in macro_refs:
                if k in self_refs:
                    continue
                visited: Set[str] = set()
                stack = list(macro_refs.get(k, set()))
                while stack:
                    node = stack.pop()
                    if node == k:
                        self_refs.add(k)
                        break
                    if node in visited:
                        continue
                    visited.add(node)
                    stack.extend(macro_refs.get(node, set()))
            for k in list(self_refs):
                visited_fwd: Set[str] = set()
                stack_fwd = list(macro_refs.get(k, set()))
                while stack_fwd:
                    node = stack_fwd.pop()
                    if node in visited_fwd:
                        continue
                    visited_fwd.add(node)
                    stack_fwd.extend(macro_refs.get(node, set()))
                for m in visited_fwd:
                    if m in macro_refs:
                        vis2: Set[str] = set()
                        stk2 = list(macro_refs.get(m, set()))
                        while stk2:
                            nd = stk2.pop()
                            if nd == k:
                                self_refs.add(m)
                                break
                            if nd in vis2:
                                continue
                            vis2.add(nd)
                            stk2.extend(macro_refs.get(nd, set()))
            self._obj_self_refs_cache = frozenset(self_refs)
            self._obj_self_refs_cache_key = cache_key
        self_refs = self._obj_self_refs_cache

        cur = line
        # First pass: allow normal expansions.
        cur = self._expand_object_like_macros_single_pass(cur, macros)

        # Subsequent rescans: suppress self-referential macros to prevent
        # runaway growth like `A -> A + 1 + 1 + ...`.
        for _ in range(19):
            nxt = self._expand_object_like_macros_single_pass(cur, macros, disabled=self_refs)
            if nxt == cur:
                return cur
            cur = nxt
        return cur

    def _expand_object_like_macros_single_pass(
        self,
        line: str,
        macros: Dict[str, str],
        *,
        disabled: Optional[Set[str]] = None,
        only_empty: bool = False,
    ) -> str:
        out: List[str] = []
        i = 0
        n = len(line)

        disabled = set(disabled or set())

        def is_ident_start(ch: str) -> bool:
            return ch.isalpha() or ch == "_"

        def is_ident_continue(ch: str) -> bool:
            return ch.isalnum() or ch == "_"

        def is_pp_number_start(ch: str) -> bool:
            return ch.isdigit() or ch == "."

        def is_pp_number_continue(ch: str) -> bool:
            return ch.isalnum() or ch in "._+-"

        # Heuristic subset: if we start expanding a macro at top-level (i.e.
        # not as a special one-shot line boundary), suppress re-expansion of
        # that same macro name while scanning its own replacement output.
        # This helps common self-referential patterns like `#define A A + 1`
        # terminate as `A + 1`.
        if disabled is None:
            disabled = set()

        while i < n:
            ch = line[i]

            # String literal
            if ch == '"':
                start = i
                i += 1
                while i < n:
                    if line[i] == "\\" and i + 1 < n:
                        i += 2
                        continue
                    if line[i] == '"':
                        i += 1
                        break
                    i += 1
                out.append(line[start:i])
                continue

            # Char literal
            if ch == "'":
                start = i
                i += 1
                while i < n:
                    if line[i] == "\\" and i + 1 < n:
                        i += 2
                        continue
                    if line[i] == "'":
                        i += 1
                        break
                    i += 1
                out.append(line[start:i])
                continue

            # Identifier token
            if is_ident_start(ch):
                start = i
                i += 1
                while i < n and is_ident_continue(line[i]):
                    i += 1
                ident = line[start:i]
                if ident in disabled:
                    out.append(ident)
                else:
                    if only_empty and ident in macros and macros[ident].strip() != "":
                        out.append(ident)
                    else:
                        if ident in macros and re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", ident):
                            # Disable the macro name for the remainder of this
                            # scan so we don't keep expanding within its own
                            # output in the same pass.
                            disabled.add(ident)
                            out.append(macros.get(ident, ident))
                        else:
                            out.append(macros.get(ident, ident))
                continue

            # Preprocessing-number (very small subset): do not expand macros
            # inside it (e.g. `0A` is one pp-number token, not `0` + `A`).
            if is_pp_number_start(ch):
                start = i
                i += 1
                while i < n and is_pp_number_continue(line[i]):
                    i += 1
                out.append(line[start:i])
                continue

            out.append(ch)
            i += 1

        return "".join(out)

    def _expand_function_like_macros(
        self,
        text: str,
        macros: Dict[str, str],
        *,
        filename: str = "",
        base_line_no: int = 1,
    ) -> str:
        # Very small subset expansion:
        # - only expands NAME(arglist) with balanced parentheses in arglist
        # - arguments are split by commas at paren depth 0
        # - supports nested expansions by iterating until no change (cap iterations)
        out = text
        for _ in range(20):
            changed = False
            for name, fn in list(self._fn_macros.items()):
                params, body, is_variadic = fn
                # Find a call site "NAME(" and expand the first one found, repeatedly.
                idx = 0
                while True:
                    call_start, paren_start = self._find_fn_macro_call(out, name, start_idx=idx)
                    if call_start is None or paren_start is None:
                        break
                    arg_text, paren_end = self._extract_paren_group(out, paren_start)
                    if paren_end is None:
                        break

                    args = self._split_args(arg_text)
                    if (not is_variadic and len(args) != len(params)) or (is_variadic and len(args) < len(params)):
                        # Best-effort: include call site line number.
                        # Convert call_start offset to a 1-based line number,
                        # relative to the current expanded string.
                        call_line = base_line_no + out[:call_start].count("\n")
                        fn = os.path.basename(filename) if filename else "<input>"
                        raise RuntimeError(
                            f"{fn}:{call_line}: unsupported macro invocation: {name} expects {len(params)} args, got {len(args)}"
                        )
                    repl = body
                    # Subset ordering:
                    # - stringize must see the original param names (#x)
                    # - token paste must see param names to combine (a##b)
                    # We therefore expand these operators per-parameter first,
                    # then substitute the remaining plain params.
                    for p, a in zip(params, args):
                        repl = self._apply_stringize(repl, p, a)
                    # Variadics: __VA_ARGS__ is the comma-joined remaining args.
                    if is_variadic:
                        va = ", ".join(args[len(params) :])
                        # Support stringizing __VA_ARGS__ via #__VA_ARGS__ (subset).
                        repl = self._apply_stringize(repl, "__VA_ARGS__", va)
                        if va.strip() == "":
                            # GNU extension (subset): swallow a preceding comma when
                            # using token paste with empty __VA_ARGS__:
                            #   , ##__VA_ARGS__  ->  (removed)
                            # We do this before the generic token-paste removal.
                            repl = re.sub(r"\s*,\s*##\s*__VA_ARGS__\b", "", repl)
                            repl = re.sub(r"\s*##\s*__VA_ARGS__\b", "", repl)
                            repl = repl.replace("__VA_ARGS__", "")
                        else:
                            repl = repl.replace("__VA_ARGS__", va)
                    # Do parameter substitution first (so a##b turns into x##y),
                    # then do token-paste removal.
                    repl = self._substitute_fn_params(repl, params=params, args=args)

                    # Subset hide-set behavior for self-referential function-like
                    # macros: if the macro's *body template* (before parameter
                    # substitution) mentions its own invocation, prevent it from
                    # expanding again during rescans.
                    # This targets common patterns like:
                    #   #define F(x) F(x) + 1
                    # so `F(0)` becomes `F(0) + 1`.
                    # IMPORTANT: only check the original body, not the substituted
                    # result, to avoid disabling legitimate nested calls that come
                    # from arguments (e.g. ADD(ADD(1,2), ADD(3,4))).
                    body_is_self_ref = bool(re.search(rf"\b{re.escape(name)}\s*\(", body))
                    if body_is_self_ref and re.search(rf"\b{re.escape(name)}\s*\(", repl):
                        # Replace only as a call: NAME( -> NAME_DISABLED(
                        repl = re.sub(
                            rf"\b{re.escape(name)}\s*\(",
                            f"{name}__PP_DISABLED__(",
                            repl,
                        )
                    # Also handle indirect recursion: if the body calls another
                    # function-like macro that eventually calls back to this one,
                    # disable the current macro in the replacement to prevent
                    # unbounded growth.  E.g. F(x)->G(x), G(x)->F(x).
                    if not body_is_self_ref:
                        cycle_macros = self._find_fn_macro_cycle(name)
                        if cycle_macros:
                            for cm in cycle_macros:
                                if re.search(rf"\b{re.escape(cm)}\s*\(", repl):
                                    repl = re.sub(
                                        rf"\b{re.escape(cm)}\s*\(",
                                        f"{cm}__PP_DISABLED__(",
                                        repl,
                                    )
                    
                    # Best-effort: only expand *empty* object-like macros inside the
                    # replacement list *before* token pasting, so common patterns like
                    # CAT(EMPTY, X) can paste correctly when EMPTY expands to nothing,
                    # without changing general token-paste semantics.
                    repl = self._expand_object_like_macros_single_pass(repl, macros, only_empty=True)
                    repl = self._apply_token_paste_simple(repl)
                    # After token pasting, rescan the pasted result for object-like macros.
                    # This is a small subset of the C preprocessor behavior.
                    # Avoid runaway growth for self-referential single-token macros
                    # (e.g. `A` -> `A + 1`) by only performing the special one-step
                    # disable when the pasted result is exactly a macro name.
                    repl_stripped = repl.strip()
                    if repl_stripped in macros and re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", repl_stripped):
                        first = self._expand_object_like_macros_single_pass(repl, macros)
                        repl = self._expand_object_like_macros_single_pass(first, macros, disabled={repl_stripped})
                    else:
                        repl = self._expand_object_like_macros(repl, macros)
                    # Recursively expand inside the replacement on subsequent passes.
                    out = out[:call_start] + repl + out[paren_end + 1 :]
                    changed = True
                    idx = call_start + len(repl)
            if not changed:
                # Restore any disabled self-referential markers.
                out = re.sub(r"\b([A-Za-z_][A-Za-z0-9_]*)__PP_DISABLED__\(", r"\1(", out)
                return out

        out = re.sub(r"\b([A-Za-z_][A-Za-z0-9_]*)__PP_DISABLED__\(", r"\1(", out)
        return out

    def _find_fn_macro_cycle(self, name: str) -> Set[str]:
        """Detect indirect recursion cycles in function-like macros.

        Returns the set of macro names involved in a cycle with `name`,
        or an empty set if no cycle exists.
        E.g. for F(x)->G(x), G(x)->F(x), calling with 'F' returns {'F', 'G'}.
        """
        # Build a reference graph for function-like macros
        fn_refs: Dict[str, Set[str]] = {}
        for k, (params, body, is_variadic) in self._fn_macros.items():
            refs: Set[str] = set()
            for other_name in self._fn_macros:
                if re.search(rf"\b{re.escape(other_name)}\s*\(", body):
                    refs.add(other_name)
            fn_refs[k] = refs

        # Check if name can reach itself through the reference graph
        visited: Set[str] = set()
        stack = list(fn_refs.get(name, set()))
        can_reach_self = False
        while stack:
            node = stack.pop()
            if node == name:
                can_reach_self = True
                break
            if node in visited:
                continue
            visited.add(node)
            stack.extend(fn_refs.get(node, set()))

        if not can_reach_self:
            return set()

        # Collect all macros in the cycle
        cycle: Set[str] = {name}
        for m in visited:
            # Check if m can reach name
            vis2: Set[str] = set()
            stk2 = list(fn_refs.get(m, set()))
            while stk2:
                nd = stk2.pop()
                if nd == name:
                    cycle.add(m)
                    break
                if nd in vis2:
                    continue
                vis2.add(nd)
                stk2.extend(fn_refs.get(nd, set()))
        return cycle

    def _find_fn_macro_call(self, text: str, name: str, *, start_idx: int) -> Tuple[Optional[int], Optional[int]]:
        """Find next function-like macro call site (subset).

        Returns (call_start, lparen_index) or (None, None) if not found.

        Subset rules:
        - Match only at identifier token boundaries.
        - Skip over string and char literals.
        - Allow whitespace between NAME and '(' (like the existing regex).
        """

        n = len(text)
        i = max(0, start_idx)

        def is_ident_start(ch: str) -> bool:
            return ch.isalpha() or ch == "_"

        def is_ident_continue(ch: str) -> bool:
            return ch.isalnum() or ch == "_"

        def is_pp_number_start(ch: str) -> bool:
            return ch.isdigit() or ch == "."

        def is_pp_number_continue(ch: str) -> bool:
            return ch.isalnum() or ch in "._+-"

        while i < n:
            ch = text[i]

            # Skip preprocessing-number tokens so we don't match identifiers
            # inside them (e.g. `0F(1)` should not match macro `F(`).
            if is_pp_number_start(ch):
                i += 1
                while i < n and is_pp_number_continue(text[i]):
                    i += 1
                continue

            # Skip string literals
            if ch == '"':
                i += 1
                while i < n:
                    if text[i] == "\\" and i + 1 < n:
                        i += 2
                        continue
                    if text[i] == '"':
                        i += 1
                        break
                    i += 1
                continue

            # Skip char literals
            if ch == "'":
                i += 1
                while i < n:
                    if text[i] == "\\" and i + 1 < n:
                        i += 2
                        continue
                    if text[i] == "'":
                        i += 1
                        break
                    i += 1
                continue

            if is_ident_start(ch):
                start = i
                i += 1
                while i < n and is_ident_continue(text[i]):
                    i += 1
                ident = text[start:i]
                if ident == name:
                    j = i
                    while j < n and text[j].isspace():
                        j += 1
                    if j < n and text[j] == "(":
                        return start, j
                continue

            i += 1

        return None, None

    def _substitute_fn_params(self, body: str, *, params: List[str], args: List[str]) -> str:
        """Substitute function-like macro params in a replacement list (subset).

        Requirements (subset):
        - only replace identifier tokens that exactly match param names
        - do not substitute inside string/char literals
        """

        if not params or not args:
            return body

        mapping = dict(zip(params, args))
        out: List[str] = []
        i = 0
        n = len(body)

        def is_ident_start(ch: str) -> bool:
            return ch.isalpha() or ch == "_"

        def is_ident_continue(ch: str) -> bool:
            return ch.isalnum() or ch == "_"

        while i < n:
            ch = body[i]

            # String literal
            if ch == '"':
                start = i
                i += 1
                while i < n:
                    if body[i] == "\\" and i + 1 < n:
                        i += 2
                        continue
                    if body[i] == '"':
                        i += 1
                        break
                    i += 1
                out.append(body[start:i])
                continue

            # Char literal
            if ch == "'":
                start = i
                i += 1
                while i < n:
                    if body[i] == "\\" and i + 1 < n:
                        i += 2
                        continue
                    if body[i] == "'":
                        i += 1
                        break
                    i += 1
                out.append(body[start:i])
                continue

            if is_ident_start(ch):
                start = i
                i += 1
                while i < n and is_ident_continue(body[i]):
                    i += 1
                ident = body[start:i]
                out.append(mapping.get(ident, ident))
                continue

            out.append(ch)
            i += 1

        return "".join(out)

    def _apply_stringize(self, body: str, param: str, arg: str) -> str:
        # Stringize (#param) per C89 §6.8.3.2:
        # - whitespace normalization: collapse runs of whitespace to single spaces
        # - escapes backslashes and double-quotes
        # - escapes tab (\t) and newline (\n) characters
        # - wraps raw argument text in double quotes
        # Only match `#param` when '#' is not part of '##'.
        def _stringize_arg(_m):
            s = re.sub(r"\s+", " ", arg.strip())
            s = s.replace("\\", "\\\\")
            s = s.replace('"', '\\"')
            s = s.replace('\t', '\\t')
            s = s.replace('\n', '\\n')
            return '"' + s + '"'
        return re.sub(
            rf"(?<!#)#\s*{re.escape(param)}\b",
            _stringize_arg,
            body,
        )

    def _apply_token_paste_simple(self, body: str) -> str:
        # Very small subset: after params are substituted, just delete the operator.
        # But reject the standard-invalid forms where '##' appears at the start
        # or end of the replacement list (subset: raise a clear error).
        # Note: after best-effort macro expansion, token pasting may end up with
        # an empty operand on either side. Accept these by dropping the operator
        # and adjacent whitespace (subset).
        body = re.sub(r"^\s*##\s*", "", body)
        body = re.sub(r"\s*##\s*$", "", body)
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
        # If arg_text is empty or only whitespace, this is a zero-argument call.
        if arg_text.strip() == "":
            return []

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
        # Important: allow empty trailing arguments (e.g. `F(a,)`), which are
        # common in macro token-paste patterns.
        tail = "".join(cur).strip()
        args.append(tail)
        return args

    def _resolve_include(
        self,
        inc_name: str,
        search_paths: List[str],
        *,
        include_stack: Optional[List[str]] = None,
        includer: Optional[str] = None,
        includer_line: Optional[int] = None,
    ) -> str:
        for d in search_paths:
            cand = os.path.abspath(os.path.join(d, inc_name))
            if os.path.isfile(cand):
                return cand
        shown = ", ".join(search_paths[:10])
        more = "" if len(search_paths) <= 10 else f" (+{len(search_paths) - 10} more)"
        loc_prefix = ""
        if includer and includer_line is not None:
            loc_prefix = f"{os.path.basename(includer)}:{includer_line}: "
        stack_msg = ""
        if include_stack:
            # Show the inclusion chain (outermost -> innermost).
            stack_msg = " (include stack: " + " -> ".join(os.path.basename(p) for p in include_stack) + ")"
        raise RuntimeError(f"{loc_prefix}cannot find include: {inc_name} (searched: {shown}{more}){stack_msg}")
