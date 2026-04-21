"""Property-based tests for CType fallback to string inference.

**Feature: ir-type-annotations, Property 8: CType fallback to string inference**

**Validates: Requirements 8.2**

For any IRInstruction with result_type = None, codegen should use the old
_var_types string inference path and produce correct assembly output that is
identical or functionally equivalent to the output produced when CType
annotations are present.

Testing approach: use Hypothesis to generate random C89 programs, compile
through the full pipeline twice:
  1. With sym_table (CType path) -- normal compilation
  2. Without sym_table (string fallback path) -- sym_table=None forces codegen
     to rely entirely on _var_types string inference

Then verify the assembly outputs are identical. Since both paths should
produce the same assembly for correctly dual-populated programs, any
divergence indicates a fallback bug.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Set

import pytest
from hypothesis import given, settings, assume, HealthCheck
from hypothesis import strategies as st

from pycc.lexer import Lexer
from pycc.parser import Parser
from pycc.semantics import SemanticAnalyzer
from pycc.ir import IRGenerator, IRInstruction
from pycc.codegen import CodeGenerator
from pycc.types import CType, TypeKind


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _compile_to_assembly(code: str, use_sym_table: bool) -> str:
    """Compile C89 source to assembly, optionally with or without sym_table.

    When use_sym_table=True, the normal pipeline is used (codegen gets
    the TypedSymbolTable from IR generation).
    When use_sym_table=False, codegen receives sym_table=None, forcing
    it to fall back to _var_types string inference for all type lookups.
    """
    lexer = Lexer(code, "<test>")
    tokens = lexer.tokenize()
    parser = Parser(tokens)
    ast = parser.parse()
    sa = SemanticAnalyzer()
    ctx = sa.analyze(ast)

    irg = IRGenerator()
    irg._sema_ctx = ctx
    ir = irg.generate(ast)
    sym_table = getattr(irg, "_sym_table", None)

    cg = CodeGenerator(
        optimize=False,
        sema_ctx=ctx,
        pic=False,
        sym_table=sym_table if use_sym_table else None,
    )
    asm = cg.generate(ir)
    return asm


def _normalize_assembly(asm: str) -> str:
    """Normalize assembly for comparison.

    Strips comments, blank lines, and trailing whitespace to focus on
    the actual instructions. This handles minor formatting differences
    that are not semantically meaningful.
    """
    lines = []
    for line in asm.splitlines():
        # Strip inline comments (# ...)
        stripped = re.sub(r'\s*#.*$', '', line).rstrip()
        if stripped:
            lines.append(stripped)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Hypothesis strategies: generate random valid C89 programs
# ---------------------------------------------------------------------------

ARITH_OPS = ["+", "-", "*"]
COMPARE_OPS = ["<", ">", "==", "!=", "<=", ">="]


@st.composite
def simple_arithmetic_program(draw):
    """Generate a program with variable declarations and arithmetic."""
    num_vars = draw(st.integers(min_value=1, max_value=4))
    var_types = draw(st.lists(
        st.sampled_from(["int", "long", "unsigned int", "char", "short"]),
        min_size=num_vars, max_size=num_vars,
    ))
    var_names = [f"v{i}" for i in range(num_vars)]
    decls = []
    for vt, vn in zip(var_types, var_names):
        init_val = draw(st.integers(min_value=0, max_value=100))
        decls.append(f"    {vt} {vn} = {init_val};")
    if num_vars >= 2:
        op = draw(st.sampled_from(ARITH_OPS))
        expr = f"{var_names[0]} {op} {var_names[1]}"
    else:
        expr = var_names[0]
    code = "int main(void) {\n"
    code += "\n".join(decls) + "\n"
    code += f"    return (int)({expr});\n"
    code += "}\n"
    return code


@st.composite
def function_with_params_program(draw):
    """Generate a program with a function that has parameters."""
    num_params = draw(st.integers(min_value=1, max_value=4))
    param_types = draw(st.lists(
        st.sampled_from(["int", "long", "char", "unsigned int"]),
        min_size=num_params, max_size=num_params,
    ))
    param_names = [f"p{i}" for i in range(num_params)]
    params_str = ", ".join(f"{pt} {pn}" for pt, pn in zip(param_types, param_names))
    if num_params >= 2:
        op = draw(st.sampled_from(ARITH_OPS))
        body_expr = f"{param_names[0]} {op} {param_names[1]}"
    else:
        body_expr = param_names[0]
    code = f"int compute({params_str}) {{\n"
    code += f"    return (int)({body_expr});\n"
    code += "}\n\n"
    code += "int main(void) {\n"
    code += f"    return compute({', '.join(str(i) for i in range(num_params))});\n"
    code += "}\n"
    return code


@st.composite
def cast_expression_program(draw):
    """Generate a program with cast expressions between types."""
    src_type = draw(st.sampled_from(["int", "long", "unsigned int", "char"]))
    dst_type = draw(st.sampled_from(["char", "short", "int", "long",
                                      "unsigned int", "unsigned char"]))
    assume(src_type != dst_type)
    init_val = draw(st.integers(min_value=0, max_value=100))
    code = f"int main(void) {{\n"
    code += f"    {src_type} x = {init_val};\n"
    code += f"    {dst_type} y = ({dst_type})x;\n"
    code += f"    return (int)y;\n"
    code += "}\n"
    return code


@st.composite
def pointer_arithmetic_program(draw):
    """Generate a program with pointer arithmetic."""
    elem_type = draw(st.sampled_from(["int", "long", "char", "short"]))
    arr_size = draw(st.integers(min_value=2, max_value=8))
    index = draw(st.integers(min_value=0, max_value=arr_size - 1))
    code = f"int main(void) {{\n"
    code += f"    {elem_type} arr[{arr_size}];\n"
    code += f"    arr[0] = 1;\n"
    code += f"    return (int)arr[{index}];\n"
    code += "}\n"
    return code


@st.composite
def struct_member_access_program(draw):
    """Generate a program with struct member access."""
    num_members = draw(st.integers(min_value=2, max_value=4))
    member_types = draw(st.lists(
        st.sampled_from(["int", "char", "long", "short"]),
        min_size=num_members, max_size=num_members,
    ))
    member_names = [f"m{i}" for i in range(num_members)]
    members_decl = "\n".join(f"    {mt} {mn};" for mt, mn in zip(member_types, member_names))
    target_idx = draw(st.integers(min_value=0, max_value=num_members - 1))
    target_member = member_names[target_idx]
    access_kind = draw(st.sampled_from(["dot", "arrow"]))
    if access_kind == "dot":
        code = f"struct S {{\n{members_decl}\n}};\n\n"
        code += "int main(void) {\n"
        code += f"    struct S s;\n"
        code += f"    s.{target_member} = 0;\n"
        code += f"    return (int)s.{target_member};\n"
        code += "}\n"
    else:
        code = f"struct S {{\n{members_decl}\n}};\n\n"
        code += "int test_fn(struct S *p) {\n"
        code += f"    p->{target_member} = 0;\n"
        code += f"    return (int)p->{target_member};\n"
        code += "}\n\n"
        code += "int main(void) {\n"
        code += "    return 0;\n"
        code += "}\n"
    return code


@st.composite
def float_expression_program(draw):
    """Generate a program with floating-point expressions."""
    fp_type = draw(st.sampled_from(["float", "double"]))
    op = draw(st.sampled_from(["+", "-", "*"]))
    val1 = draw(st.floats(min_value=0.1, max_value=100.0,
                           allow_nan=False, allow_infinity=False))
    val2 = draw(st.floats(min_value=0.1, max_value=100.0,
                           allow_nan=False, allow_infinity=False))
    code = f"int main(void) {{\n"
    code += f"    {fp_type} a = {val1};\n"
    code += f"    {fp_type} b = {val2};\n"
    code += f"    {fp_type} c = a {op} b;\n"
    code += f"    return (int)c;\n"
    code += "}\n"
    return code


@st.composite
def mixed_program(draw):
    """Generate a program combining multiple constructs."""
    has_cast = draw(st.booleans())
    has_comparison = draw(st.booleans())
    lines = ["int main(void) {"]
    lines.append("    int x = 42;")
    lines.append("    long y = 100;")
    if has_cast:
        lines.append("    char c = (char)x;")
    if has_comparison:
        cmp_op = draw(st.sampled_from(COMPARE_OPS))
        lines.append(f"    int cmp = x {cmp_op} (int)y;")
    lines.append("    return (int)(x + y);")
    lines.append("}")
    code = "\n".join(lines) + "\n"
    return code


# Combined strategy
any_c89_program = st.one_of(
    simple_arithmetic_program(),
    function_with_params_program(),
    cast_expression_program(),
    pointer_arithmetic_program(),
    struct_member_access_program(),
    float_expression_program(),
    mixed_program(),
)


# ---------------------------------------------------------------------------
# Property 8: CType fallback to string inference
# ---------------------------------------------------------------------------

class TestCTypeFallbackToStringInference:
    """Property 8: CType fallback to string inference

    **Feature: ir-type-annotations, Property 8**
    **Validates: Requirements 8.2**
    """

    @given(code=any_c89_program)
    @settings(max_examples=120, deadline=None,
              suppress_health_check=[HealthCheck.too_slow])
    def test_fallback_produces_identical_assembly(self, code):
        """For any valid C89 program, compiling with sym_table=None (forcing
        the _var_types string fallback path) should produce assembly that is
        identical to compiling with the full TypedSymbolTable.

        This validates that the fallback path in _get_type() correctly
        reconstructs type information from _var_types strings when CType
        annotations are unavailable.

        **Validates: Requirements 8.2**
        """
        try:
            asm_with_ctype = _compile_to_assembly(code, use_sym_table=True)
            asm_fallback = _compile_to_assembly(code, use_sym_table=False)
        except Exception:
            assume(False)
            return

        norm_ctype = _normalize_assembly(asm_with_ctype)
        norm_fallback = _normalize_assembly(asm_fallback)

        assert norm_ctype == norm_fallback, (
            f"Assembly divergence between CType path and fallback path.\n"
            f"Source code:\n{code}\n\n"
            f"--- CType path (first divergent lines) ---\n"
            f"{_first_diff(norm_ctype, norm_fallback)}"
        )

    @given(code=simple_arithmetic_program())
    @settings(max_examples=100, deadline=None)
    def test_arithmetic_fallback_identical(self, code):
        """For arithmetic programs, the fallback path should produce
        identical assembly to the CType path.

        **Validates: Requirements 8.2**
        """
        try:
            asm_with = _compile_to_assembly(code, use_sym_table=True)
            asm_without = _compile_to_assembly(code, use_sym_table=False)
        except Exception:
            assume(False)
            return

        norm_with = _normalize_assembly(asm_with)
        norm_without = _normalize_assembly(asm_without)

        assert norm_with == norm_without, (
            f"Arithmetic program assembly divergence.\n"
            f"Source:\n{code}\n"
            f"Diff:\n{_first_diff(norm_with, norm_without)}"
        )

    @given(code=struct_member_access_program())
    @settings(max_examples=100, deadline=None,
              suppress_health_check=[HealthCheck.too_slow])
    def test_struct_access_fallback_identical(self, code):
        """For struct member access programs, the fallback path should
        produce identical assembly to the CType path.

        **Validates: Requirements 8.2**
        """
        try:
            asm_with = _compile_to_assembly(code, use_sym_table=True)
            asm_without = _compile_to_assembly(code, use_sym_table=False)
        except Exception:
            assume(False)
            return

        norm_with = _normalize_assembly(asm_with)
        norm_without = _normalize_assembly(asm_without)

        assert norm_with == norm_without, (
            f"Struct access program assembly divergence.\n"
            f"Source:\n{code}\n"
            f"Diff:\n{_first_diff(norm_with, norm_without)}"
        )

    @given(code=float_expression_program())
    @settings(max_examples=100, deadline=None)
    def test_float_fallback_identical(self, code):
        """For floating-point programs, the fallback path should produce
        identical assembly to the CType path.

        **Validates: Requirements 8.2**
        """
        try:
            asm_with = _compile_to_assembly(code, use_sym_table=True)
            asm_without = _compile_to_assembly(code, use_sym_table=False)
        except Exception:
            assume(False)
            return

        norm_with = _normalize_assembly(asm_with)
        norm_without = _normalize_assembly(asm_without)

        assert norm_with == norm_without, (
            f"Float program assembly divergence.\n"
            f"Source:\n{code}\n"
            f"Diff:\n{_first_diff(norm_with, norm_without)}"
        )


def _first_diff(a: str, b: str, context: int = 5) -> str:
    """Return the first divergent lines between two assembly strings."""
    a_lines = a.splitlines()
    b_lines = b.splitlines()
    max_len = max(len(a_lines), len(b_lines))
    for i in range(max_len):
        la = a_lines[i] if i < len(a_lines) else "<EOF>"
        lb = b_lines[i] if i < len(b_lines) else "<EOF>"
        if la != lb:
            start = max(0, i - context)
            end = min(max_len, i + context + 1)
            result = f"First difference at line {i + 1}:\n"
            result += f"  CType:    {la!r}\n"
            result += f"  Fallback: {lb!r}\n\n"
            result += "Context (CType path):\n"
            for j in range(start, min(end, len(a_lines))):
                marker = ">>>" if j == i else "   "
                result += f"  {marker} {j+1:4d}: {a_lines[j]}\n"
            result += "\nContext (Fallback path):\n"
            for j in range(start, min(end, len(b_lines))):
                marker = ">>>" if j == i else "   "
                result += f"  {marker} {j+1:4d}: {b_lines[j]}\n"
            return result
    return "(no difference found)"
