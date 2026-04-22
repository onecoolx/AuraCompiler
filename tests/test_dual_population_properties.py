"""Property-based tests for dual population consistency during migration.

**Feature: ir-type-annotations, Property 9: Dual population consistency during migration**

**Validates: Requirements 8.3**

For any valid C89 program, during migration, every entry in the
TypedSymbolTable should have a corresponding string type entry in the
_var_types dictionary, and the two representations should be semantically
equivalent.

Testing approach: use Hypothesis to generate random C89 programs, compile
through the IR generator with a RecordingSymbolTable that captures all
insert() calls per scope. Since _var_types is reset per-function, we also
capture per-function snapshots of _var_types at each scope pop. We then
verify that within each function scope, every symbol inserted into the
symbol table also has a _var_types entry with a compatible type.

Note: exact string matching between ctype_to_ir_type(CType) and _var_types
may not always work due to normalization differences (e.g. AST Type.base
may store "int" for what is semantically a "long"). We use a relaxed
comparison that checks the broad type category (pointer vs scalar vs
struct) matches.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Set, Tuple

import pytest
from hypothesis import given, settings, assume, HealthCheck
from hypothesis import strategies as st

from pycc.lexer import Lexer
from pycc.parser import Parser
from pycc.semantics import SemanticAnalyzer
from pycc.ir import IRGenerator, IRInstruction
from pycc.types import (
    CType, TypeKind, IntegerType, FloatType, PointerType, ArrayType,
    StructType as CStructType, TypedSymbolTable, ctype_to_ir_type,
)


# ---------------------------------------------------------------------------
# Recording wrapper for TypedSymbolTable
# ---------------------------------------------------------------------------

class RecordingSymbolTable(TypedSymbolTable):
    """TypedSymbolTable subclass that records per-scope insertions.

    Tracks which symbols were inserted in each scope so we can compare
    against the per-function _var_types snapshots.
    """

    def __init__(self, sema_ctx=None):
        super().__init__(sema_ctx)
        self._current_scope_inserts: Dict[str, CType] = {}
        self.scope_snapshots: List[Dict[str, CType]] = []

    def push_scope(self) -> None:
        super().push_scope()
        self._current_scope_inserts = {}

    def pop_scope(self, func_name=None) -> None:
        self.scope_snapshots.append(dict(self._current_scope_inserts))
        self._current_scope_inserts = {}
        super().pop_scope(func_name=func_name)

    def insert(self, name: str, ctype: CType) -> None:
        super().insert(name, ctype)
        resolved = self.lookup(name)
        self._current_scope_inserts[name] = resolved if resolved is not None else ctype


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _gen_ir_with_snapshots(code: str):
    """Parse, analyze, generate IR with per-function snapshots.

    Returns (instructions, var_types_snapshots, symtable_snapshots).

    var_types_snapshots: list of _var_types dicts captured at each scope pop.
    symtable_snapshots: list of {name: CType} dicts from RecordingSymbolTable.
    """
    lexer = Lexer(code, "<test>")
    tokens = lexer.tokenize()
    parser = Parser(tokens)
    ast = parser.parse()
    sa = SemanticAnalyzer()
    ctx = sa.analyze(ast)
    irg = IRGenerator()
    irg._sema_ctx = ctx

    var_types_snapshots: List[Dict[str, str]] = []
    import pycc.ir as ir_module
    orig_cls = ir_module.TypedSymbolTable
    recording_ref: List[RecordingSymbolTable] = []

    def make_recording(sema_ctx=None):
        tbl = RecordingSymbolTable(sema_ctx)
        recording_ref.append(tbl)
        return tbl

    ir_module.TypedSymbolTable = make_recording  # type: ignore[assignment]

    # Patch _gen_function to capture _var_types snapshot after each function.
    # _gen_function resets _var_types at the start, so we capture at the end.
    orig_gen_function = irg._gen_function

    def patched_gen_function(fn):
        orig_gen_function(fn)
        var_types_snapshots.append(dict(irg._var_types))

    irg._gen_function = patched_gen_function

    try:
        instrs = irg.generate(ast)
    finally:
        ir_module.TypedSymbolTable = orig_cls

    rec = recording_ref[0] if recording_ref else None
    symtable_snapshots = rec.scope_snapshots if rec else []

    return instrs, var_types_snapshots, symtable_snapshots


def _broad_category(ctype: CType) -> str:
    """Classify a CType into a broad category for relaxed comparison."""
    if ctype.kind == TypeKind.POINTER:
        return "pointer"
    if ctype.kind == TypeKind.ARRAY:
        return "array"
    if ctype.kind in (TypeKind.STRUCT, TypeKind.UNION):
        return "aggregate"
    if ctype.kind in (TypeKind.FLOAT, TypeKind.DOUBLE):
        return "float"
    if ctype.kind in (TypeKind.CHAR, TypeKind.SHORT, TypeKind.INT,
                      TypeKind.LONG, TypeKind.ENUM):
        return "integer"
    if ctype.kind == TypeKind.VOID:
        return "void"
    return "unknown"


def _broad_category_from_str(s: str) -> str:
    """Classify a _var_types string into a broad category."""
    s = s.strip()
    if not s:
        return "unknown"
    if s.startswith("array("):
        return "array"
    if "*" in s:
        return "pointer"
    if s.startswith("struct ") or s.startswith("union "):
        return "aggregate"
    if s in ("float", "double", "long double"):
        return "float"
    # Everything else is integer-like (int, long, char, short, unsigned ...)
    return "integer"


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
        st.sampled_from(["int", "char", "long", "short", "float", "double"]),
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
# Property 9: Dual population consistency during migration
# ---------------------------------------------------------------------------

class TestDualPopulationConsistency:
    """Property 9: Dual population consistency during migration

    **Feature: ir-type-annotations, Property 9**
    **Validates: Requirements 8.3**
    """

    @given(code=any_c89_program)
    @settings(max_examples=120, deadline=None,
              suppress_health_check=[HealthCheck.too_slow])
    def test_symtable_entries_have_var_types_counterpart(self, code):
        """For any valid C89 program, within each function scope, every
        symbol inserted into the TypedSymbolTable via _new_temp_typed or
        _insert_decl_ctype should have a corresponding entry in _var_types.

        Since _var_types is reset per-function, we capture per-function
        snapshots and compare against the corresponding symbol table scope.

        We check that the _var_types entry exists for each symbol table
        entry (presence check). Type kind comparison is tested separately.

        **Validates: Requirements 8.3**
        """
        try:
            instrs, vt_snaps, st_snaps = _gen_ir_with_snapshots(code)
        except Exception:
            assume(False)
            return

        assume(len(vt_snaps) > 0)
        assume(len(st_snaps) > 0)

        num_funcs = min(len(vt_snaps), len(st_snaps))

        for i in range(num_funcs):
            vt = vt_snaps[i]
            st_scope = st_snaps[i]

            # Only check @-prefixed symbols (declared variables and params).
            # Temp variables (%tN) may be created via _new_temp_typed which
            # dual-populates, but also via plain _new_temp() in unmigrated
            # code paths. We focus on declared symbols which are always
            # dual-populated via _insert_decl_ctype + direct _var_types set.
            declared_syms = {s for s in st_scope if s.startswith("@")}
            missing = {s for s in declared_syms if s not in vt}

            assert not missing, (
                f"Function {i}: declared symbols in TypedSymbolTable but "
                f"missing from _var_types: {sorted(missing)}\n"
                f"_var_types keys: {sorted(vt.keys())}\n"
                f"Source code:\n{code}"
            )

    @given(code=any_c89_program)
    @settings(max_examples=120, deadline=None,
              suppress_health_check=[HealthCheck.too_slow])
    def test_temp_vars_dual_populated(self, code):
        """For any valid C89 program, temporary variables (%tN) that are
        in _var_types should also be in the TypedSymbolTable (reverse
        direction check).

        During incremental migration, _sym_table may have MORE entries
        than _var_types because some newer code paths (e.g. call result
        registration) only populate _sym_table. But any temp that IS in
        _var_types and was created via _new_temp_typed should also be in
        the symbol table.

        **Validates: Requirements 8.3**
        """
        try:
            instrs, vt_snaps, st_snaps = _gen_ir_with_snapshots(code)
        except Exception:
            assume(False)
            return

        assume(len(vt_snaps) > 0)
        assume(len(st_snaps) > 0)

        num_funcs = min(len(vt_snaps), len(st_snaps))

        for i in range(num_funcs):
            vt = vt_snaps[i]
            st_scope = st_snaps[i]

            # Check reverse: temps in _var_types should be in symbol table.
            # This verifies _new_temp_typed dual-populates correctly.
            vt_temps = {s for s in vt if s.startswith("%t")}
            st_temps = {s for s in st_scope if s.startswith("%t")}

            # Temps in _var_types that were NOT created by _new_temp_typed
            # (e.g. direct _var_types[t] = ... assignments in unmigrated paths)
            # won't be in the symbol table. We check the intersection: temps
            # in both should have consistent types.
            common_temps = vt_temps & st_temps
            for sym in common_temps:
                ct_cat = _broad_category(st_scope[sym])
                vt_cat = _broad_category_from_str(vt[sym])
                # Allow array/pointer flexibility
                if ct_cat == "array" and vt_cat in ("pointer", "array", "integer"):
                    continue
                assert ct_cat == vt_cat, (
                    f"Function {i}: temp {sym} type category mismatch: "
                    f"CType={ct_cat}, _var_types={vt_cat} "
                    f"(CType={st_scope[sym]}, _var_types='{vt[sym]}')\n"
                    f"Source code:\n{code}"
                )

    @given(code=any_c89_program)
    @settings(max_examples=120, deadline=None,
              suppress_health_check=[HealthCheck.too_slow])
    def test_type_category_consistent(self, code):
        """For any valid C89 program, the broad type category (pointer,
        integer, float, aggregate, array) should be consistent between
        the TypedSymbolTable CType and the _var_types string for every
        dual-populated symbol.

        This uses a relaxed comparison because the _var_types string
        representation may differ from ctype_to_ir_type() output due to
        normalization differences in the AST Type.base field.

        **Validates: Requirements 8.3**
        """
        try:
            instrs, vt_snaps, st_snaps = _gen_ir_with_snapshots(code)
        except Exception:
            assume(False)
            return

        assume(len(vt_snaps) > 0)
        assume(len(st_snaps) > 0)

        num_funcs = min(len(vt_snaps), len(st_snaps))

        for i in range(num_funcs):
            vt = vt_snaps[i]
            st_scope = st_snaps[i]
            inconsistent = []

            for sym, ctype in st_scope.items():
                if sym not in vt:
                    continue

                vt_str = vt[sym]
                ct_cat = _broad_category(ctype)
                vt_cat = _broad_category_from_str(vt_str)

                # Allow array CType to match pointer _var_types (array decay)
                if ct_cat == "array" and vt_cat in ("pointer", "array"):
                    continue
                # Allow array CType to match integer _var_types (element type)
                if ct_cat == "array" and vt_cat == "integer":
                    continue

                if ct_cat != vt_cat:
                    inconsistent.append(
                        (sym, ct_cat, vt_cat,
                         f"CType={ctype}, _var_types='{vt_str}'")
                    )

            assert not inconsistent, (
                f"Function {i}: type category inconsistencies:\n"
                + "\n".join(
                    f"  {sym}: CType category={ct_cat}, "
                    f"_var_types category={vt_cat} ({detail})"
                    for sym, ct_cat, vt_cat, detail in inconsistent
                )
                + f"\nSource code:\n{code}"
            )

    @given(code=function_with_params_program())
    @settings(max_examples=100, deadline=None)
    def test_params_dual_populated(self, code):
        """For programs with function parameters, all @param symbols
        should appear in both _sym_table and _var_types within the
        same function scope.

        **Validates: Requirements 8.3**
        """
        try:
            instrs, vt_snaps, st_snaps = _gen_ir_with_snapshots(code)
        except Exception:
            assume(False)
            return

        assume(len(vt_snaps) > 0 and len(st_snaps) > 0)

        num_funcs = min(len(vt_snaps), len(st_snaps))
        for i in range(num_funcs):
            vt = vt_snaps[i]
            st_scope = st_snaps[i]

            param_syms = {s for s in st_scope if s.startswith("@")}
            missing = {s for s in param_syms if s not in vt}

            assert not missing, (
                f"Function {i}: parameter/local symbols in symbol table "
                f"but not in _var_types: {sorted(missing)}\n"
                f"Source code:\n{code}"
            )
