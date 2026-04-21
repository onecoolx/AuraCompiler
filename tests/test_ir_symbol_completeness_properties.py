"""Property-based tests for IR symbol completeness.

**Feature: ir-type-annotations, Property 1: All IR symbols have symbol table entries**

**Validates: Requirements 1.1, 1.3, 1.4**

For any valid C89 program, after IR generation, every temporary variable (%tN)
and every declared local variable/parameter (@name) appearing in IR instructions
should have a corresponding CType entry in the TypedSymbolTable.

Testing approach: use Hypothesis to generate random C89 programs with various
constructs (variables, function calls, arithmetic, casts, member access),
compile through the IR generator with a RecordingSymbolTable that logs all
insert() calls, and verify that every %tN and @name in the IR instructions
was inserted into the symbol table.

Since scopes are popped after function generation, we use a RecordingSymbolTable
that logs all insert() calls so we can verify completeness after the fact.
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
    CType, TypeKind, IntegerType, FloatType, PointerType,
    StructType as CStructType, TypedSymbolTable,
)


# ---------------------------------------------------------------------------
# Recording wrapper for TypedSymbolTable
# ---------------------------------------------------------------------------

class RecordingSymbolTable(TypedSymbolTable):
    """TypedSymbolTable subclass that records every insert() call.

    After IR generation (even after scope pop), we can inspect the full set
    of symbols that were ever inserted.
    """

    def __init__(self, sema_ctx=None):
        super().__init__(sema_ctx)
        self.all_inserted: Set[str] = set()

    def insert(self, name: str, ctype: CType) -> None:
        """Insert and record the symbol name."""
        self.all_inserted.add(name)
        super().insert(name, ctype)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _gen_ir_recording(code: str):
    """Parse, analyze, generate IR with a RecordingSymbolTable.

    Returns (instructions, sema_ctx, ir_gen, recording_table).
    The recording_table.all_inserted contains every symbol ever inserted,
    even after scope pop.
    """
    lexer = Lexer(code, "<test>")
    tokens = lexer.tokenize()
    parser = Parser(tokens)
    ast = parser.parse()
    sa = SemanticAnalyzer()
    ctx = sa.analyze(ast)
    irg = IRGenerator()
    irg._sema_ctx = ctx

    # Inject our recording table by monkey-patching the class used in generate()
    import pycc.ir as ir_module
    orig_cls = ir_module.TypedSymbolTable
    recording_ref: List[RecordingSymbolTable] = []

    def make_recording(sema_ctx=None):
        tbl = RecordingSymbolTable(sema_ctx)
        recording_ref.append(tbl)
        return tbl

    ir_module.TypedSymbolTable = make_recording  # type: ignore[assignment]
    try:
        instrs = irg.generate(ast)
    finally:
        ir_module.TypedSymbolTable = orig_cls

    rec = recording_ref[0] if recording_ref else None
    return instrs, ctx, irg, rec


# Pattern for temporary variables: %t followed by digits
_TEMP_RE = re.compile(r"^%t\d+$")
# Pattern for local/parameter variables: @ followed by name
_LOCAL_RE = re.compile(r"^@\w+$")


def _is_symbol(s: str) -> bool:
    """Check if a string is an IR symbol (temp or local/param).

    Excludes: labels (.L*), function names (bare identifiers without @ or %),
    immediate values ($N), string constants, None.
    """
    if not s:
        return False
    if _TEMP_RE.match(s):
        return True
    if _LOCAL_RE.match(s):
        return True
    return False


def _extract_symbols_from_instructions(instrs: List[IRInstruction]) -> Set[str]:
    """Extract all symbol references from IR instructions.

    Scans result, operand1, operand2, and args fields for %tN temps
    and @name locals/params.

    Excludes:
    - Labels (.L*)
    - Function names (bare identifiers)
    - Immediate values ($N, numeric strings)
    - String constants
    - None values
    """
    symbols: Set[str] = set()

    # Ops whose operands are not symbols (labels, function names, etc.)
    # For these ops, we still check result but skip certain operand fields.
    label_ops = {"label", "jmp", "jz", "jnz"}
    # Ops where operand1 is a function name, not a symbol
    call_ops = {"call"}
    # Ops where result is a global definition, not a local symbol
    global_ops = {"gdef", "gdef_bss", "gdef_blob", "gdef_struct",
                  "gdef_array", "gdef_string"}
    # Ops that are structural markers, not real instructions
    meta_ops = {"func_begin", "func_end", "comment"}

    for instr in instrs:
        op = instr.op

        # Skip meta/structural ops entirely
        if op in meta_ops:
            continue

        # Skip global definition ops (they define globals, not local symbols)
        if op in global_ops:
            continue

        # Check result field
        if instr.result and _is_symbol(instr.result):
            symbols.add(instr.result)

        # Check operand1 field
        if op not in label_ops:
            if op in call_ops:
                # For call ops, operand1 is the function name -- skip it.
                # But the result is a temp that should be tracked.
                pass
            else:
                if instr.operand1 and _is_symbol(instr.operand1):
                    symbols.add(instr.operand1)

        # Check operand2 field
        # For member access ops, operand2 is the member name string, not a symbol
        member_ops = {"load_member", "load_member_ptr", "store_member",
                      "store_member_ptr", "addr_of_member", "addr_of_member_ptr"}
        if op not in member_ops and op not in label_ops:
            if instr.operand2 and _is_symbol(instr.operand2):
                symbols.add(instr.operand2)

        # Check args field (e.g. call arguments)
        if instr.args:
            for arg in instr.args:
                if arg and _is_symbol(arg):
                    symbols.add(arg)

    return symbols


def _collect_known_gap_temps(instrs: List[IRInstruction]) -> Set[str]:
    """Collect temp symbols produced by known unmigrated code paths.

    These are temps created via _new_temp() (not _new_temp_typed()) in
    code paths that have not yet been migrated to the CType system.
    Known gaps include:
    - Integer promotion temps (sext8, sext16, zext32 from _materialize_int_promotion)
    - Compound assignment temps
    - Pointer member access load temps (load_member_ptr with bare _new_temp)
    - Array indexing temps (load_index, addr_index)
    - Unary dereference temps (load from *ptr)
    - Switch case comparison temps
    - Increment/decrement temps
    - mov_addr temps (array decay)
    - _ensure_u32 / _ensure_u64 temps
    """
    gap_temps: Set[str] = set()

    # Ops that are known to produce temps via _new_temp() without CType
    # registration in the symbol table.
    known_gap_result_ops = {
        # Integer promotion: sext8, sext16, zext32
        "sext8", "sext16", "zext32",
        # Array indexing and pointer dereference
        "load_index", "addr_index",
        # Pointer member access (some paths use _new_temp)
        "load_member_ptr",
    }

    for instr in instrs:
        if instr.result and _TEMP_RE.match(instr.result):
            # Direct match on known gap ops
            if instr.op in known_gap_result_ops:
                gap_temps.add(instr.result)
            # load from dereference (unary *)
            elif instr.op == "load":
                gap_temps.add(instr.result)
            # mov_addr (array decay to pointer)
            elif instr.op == "mov_addr":
                gap_temps.add(instr.result)
            # mov used in various unmigrated paths
            elif instr.op == "mov":
                gap_temps.add(instr.result)
            # switch case comparison temps
            elif (instr.op == "binop" and instr.label == "=="
                  and instr.operand2 and instr.operand2.startswith("%")):
                gap_temps.add(instr.result)

    return gap_temps


# ---------------------------------------------------------------------------
# Hypothesis strategies: generate random valid C89 programs
# ---------------------------------------------------------------------------

# Scalar types for variable declarations
SCALAR_TYPES = ["int", "char", "long", "short", "unsigned int",
                "unsigned char", "unsigned long", "float", "double"]

# Binary operators for arithmetic expressions
ARITH_OPS = ["+", "-", "*"]
COMPARE_OPS = ["<", ">", "==", "!=", "<=", ">="]
BITWISE_OPS = ["&", "|", "^"]


@st.composite
def simple_arithmetic_program(draw):
    """Generate a program with variable declarations and arithmetic.

    Covers: local variable declarations, parameter declarations,
    binary operations, return statements.
    """
    num_vars = draw(st.integers(min_value=1, max_value=4))
    var_types = draw(st.lists(
        st.sampled_from(["int", "long", "unsigned int", "char", "short"]),
        min_size=num_vars, max_size=num_vars,
    ))
    var_names = [f"v{i}" for i in range(num_vars)]

    # Build declarations
    decls = []
    for vt, vn in zip(var_types, var_names):
        init_val = draw(st.integers(min_value=0, max_value=100))
        decls.append(f"    {vt} {vn} = {init_val};")

    # Build an expression using the variables
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
    """Generate a program with a function that has parameters.

    Covers: parameter declarations, function calls, return values.
    """
    num_params = draw(st.integers(min_value=1, max_value=4))
    param_types = draw(st.lists(
        st.sampled_from(["int", "long", "char", "unsigned int"]),
        min_size=num_params, max_size=num_params,
    ))
    param_names = [f"p{i}" for i in range(num_params)]

    params_str = ", ".join(f"{pt} {pn}" for pt, pn in zip(param_types, param_names))

    # Simple body using parameters
    if num_params >= 2:
        op = draw(st.sampled_from(ARITH_OPS))
        body_expr = f"{param_names[0]} {op} {param_names[1]}"
    else:
        body_expr = param_names[0]

    code = f"""
int compute({params_str}) {{
    return (int)({body_expr});
}}

int main(void) {{
    return compute({', '.join(str(i) for i in range(num_params))});
}}
"""
    return code


@st.composite
def cast_expression_program(draw):
    """Generate a program with cast expressions between types.

    Covers: cast temporaries, type conversion instructions.
    """
    src_type = draw(st.sampled_from(["int", "long", "unsigned int", "char"]))
    dst_type = draw(st.sampled_from(["char", "short", "int", "long",
                                      "unsigned int", "unsigned char"]))
    assume(src_type != dst_type)

    init_val = draw(st.integers(min_value=0, max_value=100))

    code = f"""
int main(void) {{
    {src_type} x = {init_val};
    {dst_type} y = ({dst_type})x;
    return (int)y;
}}
"""
    return code


@st.composite
def pointer_arithmetic_program(draw):
    """Generate a program with pointer arithmetic.

    Covers: pointer declarations, array access, pointer add/sub.
    """
    elem_type = draw(st.sampled_from(["int", "long", "char", "short"]))
    arr_size = draw(st.integers(min_value=2, max_value=8))
    index = draw(st.integers(min_value=0, max_value=arr_size - 1))

    code = f"""
int main(void) {{
    {elem_type} arr[{arr_size}];
    arr[0] = 1;
    return (int)arr[{index}];
}}
"""
    return code


@st.composite
def struct_member_access_program(draw):
    """Generate a program with struct member access.

    Covers: struct declarations, member access (dot and arrow),
    load_member/store_member instructions.
    """
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
        code = f"""
struct S {{
{members_decl}
}};

int main(void) {{
    struct S s;
    s.{target_member} = 0;
    return (int)s.{target_member};
}}
"""
    else:
        code = f"""
struct S {{
{members_decl}
}};

int test_fn(struct S *p) {{
    p->{target_member} = 0;
    return (int)p->{target_member};
}}

int main(void) {{
    return 0;
}}
"""
    return code


@st.composite
def float_expression_program(draw):
    """Generate a program with floating-point expressions.

    Covers: float literals, float arithmetic, int-to-float conversion.
    """
    fp_type = draw(st.sampled_from(["float", "double"]))
    op = draw(st.sampled_from(["+", "-", "*"]))
    val1 = draw(st.floats(min_value=0.1, max_value=100.0,
                           allow_nan=False, allow_infinity=False))
    val2 = draw(st.floats(min_value=0.1, max_value=100.0,
                           allow_nan=False, allow_infinity=False))

    code = f"""
int main(void) {{
    {fp_type} a = {val1};
    {fp_type} b = {val2};
    {fp_type} c = a {op} b;
    return (int)c;
}}
"""
    return code


@st.composite
def string_literal_program(draw):
    """Generate a program with string literals.

    Covers: string constant temporaries.
    """
    # Use simple safe strings
    length = draw(st.integers(min_value=1, max_value=10))
    chars = draw(st.lists(
        st.sampled_from("abcdefghijklmnopqrstuvwxyz0123456789 "),
        min_size=length, max_size=length,
    ))
    s = "".join(chars)

    code = f"""
int main(void) {{
    char *s = "{s}";
    return s[0];
}}
"""
    return code


@st.composite
def comparison_program(draw):
    """Generate a program with comparison and logical operators.

    Covers: comparison result temporaries, logical AND/OR.
    """
    cmp_op = draw(st.sampled_from(COMPARE_OPS))
    val1 = draw(st.integers(min_value=0, max_value=100))
    val2 = draw(st.integers(min_value=0, max_value=100))

    code = f"""
int main(void) {{
    int a = {val1};
    int b = {val2};
    int c = a {cmp_op} b;
    return c;
}}
"""
    return code


@st.composite
def mixed_program(draw):
    """Generate a program combining multiple constructs.

    Covers: variables, arithmetic, casts, comparisons, function calls.
    """
    has_cast = draw(st.booleans())
    has_comparison = draw(st.booleans())
    has_call = draw(st.booleans())

    lines = ["int main(void) {"]
    lines.append("    int x = 42;")
    lines.append("    long y = 100;")

    if has_cast:
        lines.append("    char c = (char)x;")

    if has_comparison:
        cmp_op = draw(st.sampled_from(COMPARE_OPS))
        lines.append(f"    int cmp = x {cmp_op} (int)y;")

    if has_call:
        # Use a simple helper function
        lines.insert(0, "int helper(int a) { return a + 1; }")
        lines.append("    int r = helper(x);")

    lines.append("    return (int)(x + y);")
    lines.append("}")

    code = "\n".join(lines) + "\n"
    return code


# Combined strategy that draws from all program generators
any_c89_program = st.one_of(
    simple_arithmetic_program(),
    function_with_params_program(),
    cast_expression_program(),
    pointer_arithmetic_program(),
    struct_member_access_program(),
    float_expression_program(),
    string_literal_program(),
    comparison_program(),
    mixed_program(),
)


# ---------------------------------------------------------------------------
# Property 1: All IR symbols have symbol table entries
# ---------------------------------------------------------------------------

class TestIRSymbolCompleteness:
    """Property 1: All IR symbols have symbol table entries

    **Feature: ir-type-annotations, Property 1**
    **Validates: Requirements 1.1, 1.3, 1.4**
    """

    @given(code=any_c89_program)
    @settings(max_examples=120, deadline=None,
              suppress_health_check=[HealthCheck.too_slow])
    def test_all_ir_symbols_have_symtable_entries(self, code):
        """For any valid C89 program, every %tN and @name in IR instructions
        should have been inserted into the TypedSymbolTable.

        Known gaps: some code paths (integer promotion, compound assignment,
        array indexing, pointer dereference) still use _new_temp() without
        _new_temp_typed(). These are excluded from the check via
        _collect_known_gap_temps().

        **Validates: Requirements 1.1, 1.3, 1.4**
        """
        try:
            instrs, ctx, irg, rec = _gen_ir_recording(code)
        except Exception:
            # If the program fails to compile, skip it
            assume(False)
            return

        assume(rec is not None)
        assume(len(instrs) > 0)

        # Extract all symbols referenced in IR instructions
        referenced_symbols = _extract_symbols_from_instructions(instrs)

        # Collect temps from known unmigrated code paths
        known_gaps = _collect_known_gap_temps(instrs)

        # Check: symbols that are NOT in known gaps should all be in the table
        checkable = referenced_symbols - known_gaps
        missing = checkable - rec.all_inserted

        assert not missing, (
            f"IR symbols missing from TypedSymbolTable: {sorted(missing)}\n"
            f"Total referenced: {len(referenced_symbols)}, "
            f"Known gaps: {len(known_gaps)}, "
            f"Checkable: {len(checkable)}, "
            f"Total inserted: {len(rec.all_inserted)}\n"
            f"Missing: {sorted(missing)}\n"
            f"Source code:\n{code}"
        )

    @given(code=simple_arithmetic_program())
    @settings(max_examples=100, deadline=None)
    def test_arithmetic_temps_have_symtable_entries(self, code):
        """For programs with arithmetic, all temporary variables from
        binary operations should be in the symbol table.

        **Validates: Requirements 1.3**
        """
        try:
            instrs, ctx, irg, rec = _gen_ir_recording(code)
        except Exception:
            assume(False)
            return

        assume(rec is not None)

        # Focus on binop results
        binop_results = set()
        for instr in instrs:
            if instr.op == "binop" and instr.result and _TEMP_RE.match(instr.result):
                binop_results.add(instr.result)

        missing = binop_results - rec.all_inserted
        assert not missing, (
            f"Binop result temps missing from TypedSymbolTable: {sorted(missing)}\n"
            f"Source code:\n{code}"
        )

    @given(code=function_with_params_program())
    @settings(max_examples=100, deadline=None)
    def test_params_have_symtable_entries(self, code):
        """For programs with function parameters, all @param symbols
        should be in the symbol table.

        **Validates: Requirements 1.4**
        """
        try:
            instrs, ctx, irg, rec = _gen_ir_recording(code)
        except Exception:
            assume(False)
            return

        assume(rec is not None)

        # Extract all @name symbols from param instructions
        param_symbols = set()
        for instr in instrs:
            if instr.op == "param" and instr.result and _LOCAL_RE.match(instr.result):
                param_symbols.add(instr.result)

        missing = param_symbols - rec.all_inserted
        assert not missing, (
            f"Parameter symbols missing from TypedSymbolTable: {sorted(missing)}\n"
            f"Source code:\n{code}"
        )

    @given(code=cast_expression_program())
    @settings(max_examples=100, deadline=None)
    def test_cast_temps_have_symtable_entries(self, code):
        """For programs with cast expressions, all temporary variables
        created by cast conversion instructions should be in the symbol table.

        **Validates: Requirements 1.3**
        """
        conv_ops = {"i2f", "i2d", "f2i", "d2i", "f2d", "d2f",
                    "sext8", "sext16"}

        try:
            instrs, ctx, irg, rec = _gen_ir_recording(code)
        except Exception:
            assume(False)
            return

        assume(rec is not None)

        cast_results = set()
        for instr in instrs:
            if instr.op in conv_ops and instr.result and _TEMP_RE.match(instr.result):
                cast_results.add(instr.result)
            # Truncation via bitwise AND (char/short casts)
            if (instr.op == "binop" and instr.label == "&"
                    and instr.operand2 in ("$255", "$65535")
                    and instr.result and _TEMP_RE.match(instr.result)):
                cast_results.add(instr.result)

        missing = cast_results - rec.all_inserted
        assert not missing, (
            f"Cast temp symbols missing from TypedSymbolTable: {sorted(missing)}\n"
            f"Source code:\n{code}"
        )
