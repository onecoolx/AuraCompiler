"""
GCC Extension Stripper

Removes GCC-specific extensions from preprocessed C source text before
it reaches the lexer. Uses character-scanning with bracket matching
rather than regex to correctly handle nested parentheses.

Handles:
- __attribute__((anything))  including nested parens
- __extension__
- __asm__("anything") / __asm__ volatile("anything")
- __inline / __inline__
- __restrict / __restrict__
- _Float128/_Float64/_Float32/_Float64x/_Float32x -> standard C types
"""

from __future__ import annotations

# Mapping from GCC _Float* types to standard C types.
# Ordered longest-first so _Float128 is checked before _Float32, etc.
_FLOAT_TYPE_MAP = {
    "_Float128": "long double",
    "_Float64x": "long double",
    "_Float64":  "double",
    "_Float32x": "double",
    "_Float32":  "float",
}

# GCC extension: 128-bit integer types → map to 64-bit (lossy but allows
# compilation of code that uses __int128 for high-precision intermediates).
_INT128_TYPE_MAP = {
    "__uint128_t": "unsigned long",
    "__int128_t":  "long",
    "__int128":    "long",
}

# Simple keywords to remove (replaced with empty string).
_SIMPLE_KEYWORDS = (
    "__extension__",
    "__inline__",
    "__inline",
    "__restrict__",
    "__restrict",
)

# GCC extension: alternative keyword spellings → standard C equivalents.
_KEYWORD_REPLACEMENTS = {
    "__signed__": "signed",
    "__signed":   "signed",
}


def strip_gcc_extensions(text: str) -> str:
    """Strip GCC extensions from preprocessed C source text.

    Single-pass character scanner that:
    1. Skips string/char literals (preserving their content)
    2. Removes __attribute__((...)) with nested paren matching
    3. Removes __asm__(...) / __asm__ volatile(...)
    4. Removes simple keywords: __extension__, __inline, __inline__, etc.
    5. Replaces _Float* types with standard C equivalents

    Returns the cleaned text. If no extensions are found, returns the
    input unchanged.
    """
    if not text:
        return text

    out: list[str] = []
    i = 0
    n = len(text)

    while i < n:
        c = text[i]

        # --- String literal protection ---
        if c == '"' or c == "'":
            # Copy the entire string/char literal verbatim.
            quote = c
            out.append(c)
            i += 1
            while i < n:
                ch = text[i]
                out.append(ch)
                if ch == '\\' and i + 1 < n:
                    # Escaped character: copy next char too.
                    i += 1
                    out.append(text[i])
                elif ch == quote:
                    break
                i += 1
            i += 1
            continue

        # --- __attribute__((...)) ---
        if c == '_' and text[i:i+13] == '__attribute__':
            if _is_word_boundary(text, i, 13):
                end = _skip_attribute(text, i)
                if end is not None:
                    i = end
                    continue

        # --- __asm__ / __asm__ volatile ---
        if c == '_' and text[i:i+7] == '__asm__':
            if _is_word_boundary(text, i, 7):
                end = _skip_asm(text, i)
                if end is not None:
                    i = end
                    continue

        # --- Simple keyword removal ---
        if c == '_':
            matched = False
            for kw in _SIMPLE_KEYWORDS:
                kw_len = len(kw)
                if text[i:i+kw_len] == kw and _is_word_boundary(text, i, kw_len):
                    # Remove keyword (replace with space to avoid token merging)
                    out.append(' ')
                    i += kw_len
                    matched = True
                    break
            if not matched:
                # --- GCC extension: alternative keyword spellings ---
                for kw, replacement in _KEYWORD_REPLACEMENTS.items():
                    kw_len = len(kw)
                    if text[i:i+kw_len] == kw and _is_word_boundary(text, i, kw_len):
                        out.append(replacement)
                        i += kw_len
                        matched = True
                        break
            if matched:
                continue

        # --- _Float* type replacement ---
        if c == '_' and i + 6 <= n and text[i:i+6] == '_Float':
            replaced = False
            for ftype, replacement in _FLOAT_TYPE_MAP.items():
                ft_len = len(ftype)
                if text[i:i+ft_len] == ftype and _is_word_boundary(text, i, ft_len):
                    out.append(replacement)
                    i += ft_len
                    replaced = True
                    break
            if replaced:
                continue

        # --- GCC extension: __uint128_t / __int128_t / __int128 type replacement ---
        if c == '_' and i + 6 <= n and text[i:i+6] == '__int1' or (c == '_' and i + 6 <= n and text[i:i+7] == '__uint1'):
            replaced = False
            for itype, replacement in _INT128_TYPE_MAP.items():
                it_len = len(itype)
                if text[i:i+it_len] == itype and _is_word_boundary(text, i, it_len):
                    out.append(replacement)
                    i += it_len
                    replaced = True
                    break
            if replaced:
                continue

        # --- Default: copy character ---
        out.append(c)
        i += 1

    return ''.join(out)


def _is_word_boundary(text: str, pos: int, length: int) -> bool:
    """Check that the match at text[pos:pos+length] is a whole word.

    Returns True if the character before pos (if any) and the character
    after pos+length (if any) are not identifier characters.
    """
    # Check character before
    if pos > 0 and _is_ident_char(text[pos - 1]):
        return False
    # Check character after
    end = pos + length
    if end < len(text) and _is_ident_char(text[end]):
        return False
    return True


def _is_ident_char(c: str) -> bool:
    """Return True if c is a valid C identifier character."""
    return c.isalnum() or c == '_'


def _skip_whitespace(text: str, i: int) -> int:
    """Advance past whitespace characters."""
    n = len(text)
    while i < n and text[i] in (' ', '\t', '\n', '\r'):
        i += 1
    return i


def _skip_attribute(text: str, pos: int) -> int | None:
    """Skip __attribute__((...)) starting at pos.

    Uses a depth counter to handle arbitrarily nested parentheses.
    Returns the position after the closing '))' or None if malformed.
    """
    n = len(text)
    i = pos + 13  # skip '__attribute__'
    i = _skip_whitespace(text, i)

    # Expect '(('
    if i >= n or text[i] != '(':
        return None
    i += 1
    if i >= n or text[i] != '(':
        return None

    # Now scan with depth counter starting at 2 (we've seen '((')
    depth = 2
    i += 1
    while i < n and depth > 0:
        c = text[i]
        if c == '(':
            depth += 1
        elif c == ')':
            depth -= 1
        elif c == '"' or c == "'":
            # Skip string/char literals inside attribute
            i = _skip_string_literal(text, i)
            continue
        i += 1

    if depth != 0:
        # Unmatched parens: leave original text
        return None
    return i


def _skip_asm(text: str, pos: int) -> int | None:
    """Skip __asm__(...) or __asm__ volatile(...) starting at pos.

    Returns the position after the closing ')' or None if malformed.
    """
    n = len(text)
    i = pos + 7  # skip '__asm__'
    i = _skip_whitespace(text, i)

    # Optional 'volatile' keyword
    if i < n and text[i:i+8] == 'volatile':
        i += 8
        i = _skip_whitespace(text, i)

    # Expect '('
    if i >= n or text[i] != '(':
        return None

    # Scan with depth counter
    depth = 1
    i += 1
    while i < n and depth > 0:
        c = text[i]
        if c == '(':
            depth += 1
        elif c == ')':
            depth -= 1
        elif c == '"' or c == "'":
            i = _skip_string_literal(text, i)
            continue
        i += 1

    if depth != 0:
        return None
    return i


def _skip_string_literal(text: str, pos: int) -> int:
    """Skip a string or char literal starting at pos.

    Returns the position of the character after the closing quote.
    """
    n = len(text)
    quote = text[pos]
    i = pos + 1
    while i < n:
        c = text[i]
        if c == '\\' and i + 1 < n:
            i += 2  # skip escaped char
            continue
        if c == quote:
            return i + 1
        i += 1
    # Unterminated literal: return end of text
    return n
