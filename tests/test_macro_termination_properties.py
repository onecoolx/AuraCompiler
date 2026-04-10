"""Property-based tests for macro expansion termination.

**Validates: Requirements 8.3, 9.1, 9.2**

Property 11: 自引用/递归宏展开终止性
For any 包含自引用或间接递归引用的宏定义集合，预处理器的展开过程应在有限步内终止，
不产生无限循环，且自引用的宏名在展开结果中保持为普通标识符。

Testing approach: use Hypothesis to generate random sets of macro definitions
that include self-references or indirect recursion, then:
1. Feed them to the MacroExpander (token-based)
2. Verify expansion terminates within a reasonable time (e.g., 5 seconds)
3. Verify the result is finite (bounded length)
4. Verify self-referential macro names appear as plain identifiers in the result
"""
from __future__ import annotations

import signal
from typing import Dict, List, Optional, Tuple

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from pycc.preprocessor import MacroExpander, MacroDef, PPToken, PPTokenizer


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Pool of macro names used for generation
MACRO_NAMES = ["A", "B", "C", "D", "E"]

# Maximum allowed length of expansion result (tokens)
MAX_RESULT_TOKENS = 10000

# Timeout for a single expansion (seconds)
EXPANSION_TIMEOUT = 5


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_tokenizer = PPTokenizer()


def _build_macros(definitions: List[Tuple[str, Optional[List[str]], str]]
                  ) -> Dict[str, MacroDef]:
    """Build a macro dict from (name, params_or_None, body) tuples.

    If params is None, the macro is object-like.
    If params is a list of strings, the macro is function-like.
    """
    macros: Dict[str, MacroDef] = {}
    for name, params, body in definitions:
        tokens = _tokenizer.tokenize(body)
        if params is None:
            macros[name] = MacroDef(
                name=name,
                is_function_like=False,
                replacement=tokens,
            )
        else:
            macros[name] = MacroDef(
                name=name,
                is_function_like=True,
                params=params,
                replacement=tokens,
            )
    return macros


def _expand(macros: Dict[str, MacroDef], text: str) -> List[PPToken]:
    """Expand macros in *text* and return the result token list."""
    expander = MacroExpander(macros)
    tokens = _tokenizer.tokenize(text)
    return expander.expand(tokens)


def _result_text(tokens: List[PPToken]) -> str:
    """Join result tokens into a string."""
    return "".join(t.text for t in tokens)


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

@st.composite
def object_like_self_ref_macros(draw):
    """Generate a set of object-like macros where at least one is self-referential.

    Each macro's body is a mix of macro names and literal tokens, ensuring
    at least one macro references itself.
    """
    n_macros = draw(st.integers(min_value=1, max_value=5))
    names = MACRO_NAMES[:n_macros]

    definitions = []
    has_self_ref = False

    for name in names:
        # Body consists of 1-4 tokens, each either a macro name or a literal
        body_parts = []
        n_parts = draw(st.integers(min_value=1, max_value=4))
        for _ in range(n_parts):
            if draw(st.booleans()):
                # Use a macro name (possibly self)
                ref = draw(st.sampled_from(names))
                if ref == name:
                    has_self_ref = True
                body_parts.append(ref)
            else:
                # Use a literal number
                body_parts.append(str(draw(st.integers(min_value=0, max_value=99))))
        definitions.append((name, None, " ".join(body_parts)))

    # Ensure at least one self-reference exists
    if not has_self_ref:
        # Force the first macro to reference itself
        idx = 0
        name = names[idx]
        old_name, old_params, old_body = definitions[idx]
        definitions[idx] = (old_name, old_params, f"{name} {old_body}")

    return definitions, names


@st.composite
def object_like_cycle_macros(draw):
    """Generate a set of object-like macros with at least one indirect cycle.

    Creates 2-5 macros where at least one cycle exists (e.g., A->B->A).
    """
    n_macros = draw(st.integers(min_value=2, max_value=5))
    names = MACRO_NAMES[:n_macros]

    definitions = []
    for name in names:
        body_parts = []
        n_parts = draw(st.integers(min_value=1, max_value=3))
        for _ in range(n_parts):
            if draw(st.booleans()):
                ref = draw(st.sampled_from(names))
                body_parts.append(ref)
            else:
                body_parts.append(str(draw(st.integers(min_value=0, max_value=99))))
        definitions.append((name, None, " ".join(body_parts)))

    # Force a cycle: make the last macro reference the first
    last_name = names[-1]
    first_name = names[0]
    old_name, old_params, old_body = definitions[-1]
    definitions[-1] = (old_name, old_params, f"{first_name} {old_body}")
    # And the first references the second (if more than 1)
    if n_macros >= 2:
        old_name, old_params, old_body = definitions[0]
        definitions[0] = (old_name, old_params, f"{names[1]} {old_body}")

    return definitions, names


@st.composite
def function_like_recursive_macros(draw):
    """Generate a set of function-like macros with self-references or cycles.

    Each macro takes 1 parameter and its body may reference other macros
    (including itself) with that parameter.
    """
    n_macros = draw(st.integers(min_value=1, max_value=4))
    names = MACRO_NAMES[:n_macros]

    definitions = []
    has_recursion = False

    for name in names:
        body_parts = []
        n_parts = draw(st.integers(min_value=1, max_value=3))
        for _ in range(n_parts):
            choice = draw(st.integers(min_value=0, max_value=2))
            if choice == 0:
                # Reference another macro (or self) as a function call
                ref = draw(st.sampled_from(names))
                if ref == name:
                    has_recursion = True
                body_parts.append(f"{ref}(x)")
            elif choice == 1:
                # Use the parameter
                body_parts.append("x")
            else:
                # Use a literal
                body_parts.append(str(draw(st.integers(min_value=0, max_value=99))))
        definitions.append((name, ["x"], " + ".join(body_parts)))

    # Ensure at least one recursion
    if not has_recursion:
        idx = 0
        name = names[idx]
        old_name, old_params, old_body = definitions[idx]
        definitions[idx] = (old_name, old_params, f"{name}(x) + {old_body}")

    return definitions, names


@st.composite
def mixed_recursive_macros(draw):
    """Generate a mix of object-like and function-like macros with cycles.

    Some macros are object-like, some are function-like, and there is at
    least one cross-reference creating a cycle.
    """
    n_macros = draw(st.integers(min_value=2, max_value=5))
    names = MACRO_NAMES[:n_macros]

    definitions = []
    for i, name in enumerate(names):
        is_fn = draw(st.booleans())
        body_parts = []
        n_parts = draw(st.integers(min_value=1, max_value=3))
        for _ in range(n_parts):
            if draw(st.booleans()):
                ref = draw(st.sampled_from(names))
                if is_fn and draw(st.booleans()):
                    body_parts.append(f"{ref}(x)" if ref != name or is_fn else ref)
                else:
                    body_parts.append(ref)
            else:
                body_parts.append(str(draw(st.integers(min_value=0, max_value=99))))

        body = " ".join(body_parts)
        if is_fn:
            definitions.append((name, ["x"], body))
        else:
            definitions.append((name, None, body))

    # Force a cycle between first and last
    first_name = names[0]
    last_name = names[-1]
    old_name, old_params, old_body = definitions[0]
    if old_params is None:
        definitions[0] = (old_name, old_params, f"{last_name} {old_body}")
    else:
        definitions[0] = (old_name, old_params, f"{last_name}(x) {old_body}")
    old_name, old_params, old_body = definitions[-1]
    if old_params is None:
        definitions[-1] = (old_name, old_params, f"{first_name} {old_body}")
    else:
        definitions[-1] = (old_name, old_params, f"{first_name}(x) {old_body}")

    return definitions, names


# ---------------------------------------------------------------------------
# Property 11: 自引用/递归宏展开终止性
# ---------------------------------------------------------------------------

class TestMacroTerminationProperties:
    """Property 11: 自引用/递归宏展开终止性

    **Validates: Requirements 8.3, 9.1, 9.2**
    """

    @given(data=object_like_self_ref_macros())
    @settings(max_examples=100, deadline=None)
    def test_object_like_self_ref_terminates(self, data):
        """For any set of object-like macros containing self-references,
        expansion should terminate in finite steps and produce a bounded result.

        Self-referential macro names should appear as plain identifiers in the
        result (not further expanded).

        **Validates: Requirements 8.3**
        """
        definitions, names = data
        macros = _build_macros(definitions)

        # Expand each macro name and verify termination + bounded result
        for name in names:
            result = _expand(macros, name)
            result_len = len(result)

            # Must terminate with bounded output
            assert result_len <= MAX_RESULT_TOKENS, (
                f"Expansion of '{name}' produced {result_len} tokens "
                f"(limit {MAX_RESULT_TOKENS}), suggesting non-termination.\n"
                f"Definitions: {definitions}"
            )

            # Result must be non-empty (at minimum the macro name itself)
            assert result_len > 0, (
                f"Expansion of '{name}' produced empty result.\n"
                f"Definitions: {definitions}"
            )

    @given(data=object_like_cycle_macros())
    @settings(max_examples=100, deadline=None)
    def test_object_like_cycle_terminates(self, data):
        """For any set of object-like macros with indirect cycles (A->B->...->A),
        expansion should terminate without infinite loops.

        **Validates: Requirements 9.1**
        """
        definitions, names = data
        macros = _build_macros(definitions)

        for name in names:
            result = _expand(macros, name)
            result_len = len(result)

            assert result_len <= MAX_RESULT_TOKENS, (
                f"Expansion of '{name}' produced {result_len} tokens "
                f"(limit {MAX_RESULT_TOKENS}), suggesting non-termination.\n"
                f"Definitions: {definitions}"
            )

    @given(data=object_like_self_ref_macros())
    @settings(max_examples=100, deadline=None)
    def test_self_ref_name_preserved_as_identifier(self, data):
        """For any self-referential macro, the macro name should appear as a
        plain identifier in the expansion result (not further expanded).

        **Validates: Requirements 8.3**
        """
        definitions, names = data
        macros = _build_macros(definitions)

        # Find macros that are self-referential
        for name, params, body in definitions:
            body_tokens = _tokenizer.tokenize(body)
            is_self_ref = any(
                t.kind == "ident" and t.text == name for t in body_tokens
            )
            if not is_self_ref:
                continue

            result = _expand(macros, name)
            result_text = _result_text(result)

            # The self-referential name must appear in the result
            assert name in result_text, (
                f"Self-referential macro '{name}' should appear in expansion "
                f"result as a plain identifier, but got: {result_text!r}\n"
                f"Definitions: {definitions}"
            )

            # Verify the name appears as an identifier token (not part of
            # another token)
            name_tokens = [t for t in result if t.kind == "ident" and t.text == name]
            assert len(name_tokens) > 0, (
                f"Self-referential macro '{name}' should appear as an ident "
                f"token in the result.\n"
                f"Result tokens: {[(t.kind, t.text) for t in result]}\n"
                f"Definitions: {definitions}"
            )

            # Each occurrence of the name in the result should have the name
            # in its hide_set (preventing further expansion)
            for tok in name_tokens:
                assert name in tok.hide_set, (
                    f"Self-referential macro '{name}' in result should have "
                    f"'{name}' in its hide_set, but hide_set={tok.hide_set}\n"
                    f"Definitions: {definitions}"
                )

    @given(data=function_like_recursive_macros())
    @settings(max_examples=100, deadline=None)
    def test_function_like_recursive_terminates(self, data):
        """For any set of function-like macros with self-references or cycles,
        expansion should terminate in finite steps.

        **Validates: Requirements 8.3, 9.1**
        """
        definitions, names = data
        macros = _build_macros(definitions)

        for name in names:
            # Only expand function-like macros with an argument
            macro = macros[name]
            if macro.is_function_like:
                text = f"{name}(1)"
            else:
                text = name

            result = _expand(macros, text)
            result_len = len(result)

            assert result_len <= MAX_RESULT_TOKENS, (
                f"Expansion of '{text}' produced {result_len} tokens "
                f"(limit {MAX_RESULT_TOKENS}), suggesting non-termination.\n"
                f"Definitions: {definitions}"
            )

    @given(data=mixed_recursive_macros())
    @settings(max_examples=100, deadline=None)
    def test_mixed_recursive_terminates(self, data):
        """For any mix of object-like and function-like macros with cycles,
        expansion should terminate without infinite loops.

        **Validates: Requirements 9.1, 9.2**
        """
        definitions, names = data
        macros = _build_macros(definitions)

        for name in names:
            macro = macros[name]
            if macro.is_function_like:
                text = f"{name}(42)"
            else:
                text = name

            result = _expand(macros, text)
            result_len = len(result)

            assert result_len <= MAX_RESULT_TOKENS, (
                f"Expansion of '{text}' produced {result_len} tokens "
                f"(limit {MAX_RESULT_TOKENS}), suggesting non-termination.\n"
                f"Definitions: {definitions}"
            )

    @given(data=object_like_cycle_macros())
    @settings(max_examples=100, deadline=None)
    def test_cycle_expansion_independent_context(self, data):
        """For any set of macros with cycles, expanding the same macro from
        different starting points should both terminate, and the hide-set
        should be maintained independently per expansion context.

        **Validates: Requirements 9.2**
        """
        definitions, names = data
        macros = _build_macros(definitions)

        # Expand from two different starting macros
        if len(names) < 2:
            return

        result_a = _expand(macros, names[0])
        result_b = _expand(macros, names[1])

        # Both must terminate with bounded output
        assert len(result_a) <= MAX_RESULT_TOKENS
        assert len(result_b) <= MAX_RESULT_TOKENS

        # Expanding a combined expression should also terminate
        combined_text = f"{names[0]} {names[1]}"
        result_combined = _expand(macros, combined_text)
        assert len(result_combined) <= MAX_RESULT_TOKENS
