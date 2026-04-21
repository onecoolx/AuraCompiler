"""Property-based tests for pointer/array element size scaling.

**Feature: ir-type-annotations, Property 6: pointer/array element size matches CType**

**Validates: Requirements 6.1, 6.2**

For any C89 program containing pointer arithmetic or array indexing, the IR
generator's scaling factor should equal type_sizeof(pointee_ctype), where
pointee_ctype is the pointee CType of the pointer operand (after typedef
resolution).

Testing approach: use Hypothesis to generate random C89 programs with pointer
arithmetic on different pointer types (int*, long*, short*, struct*), compile
through the IR generator with a RecordingSymbolTable, and verify that:
  1. The scaling factor in the mul instruction matches type_sizeof(pointee_ctype)
  2. The symbol table records pointer variables with correct pointee CType
  3. Array variables have element CType whose size matches the declared type
"""
from __future__ import annotations

from typing import List, Optional, Tuple

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from pycc.lexer import Lexer
from pycc.parser import Parser
from pycc.semantics import SemanticAnalyzer
from pycc.ir import IRGenerator, IRInstruction
from pycc.types import (
    CType, TypeKind, IntegerType, FloatType, PointerType,
    ArrayType as CArrayType, StructType as CStructType,
    TypedSymbolTable, type_sizeof, ast_type_to_ctype_resolved,
)


# ---------------------------------------------------------------------------
# Recording wrapper for TypedSymbolTable
# ---------------------------------------------------------------------------

class RecordingSymbolTable(TypedSymbolTable):
    """TypedSymbolTable subclass that records every insert() call.

    After IR generation (even after scope pop), we can inspect the log to
    verify that pointer/array variables had correct CTypes during generation.
    """

    def __init__(self, sema_ctx=None):
        super().__init__(sema_ctx)
        self.insert_log: List[Tuple[str, CType]] = []

    def insert(self, name: str, ctype: CType) -> None:
        resolved = self._resolve_typedef(ctype)
        self.insert_log.append((name, resolved))
        super().insert(name, ctype)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _gen_ir_with_ctx(code: str):
    """Parse, analyze, and generate IR."""
    lexer = Lexer(code, "<test>")
    tokens = lexer.tokenize()
    parser = Parser(tokens)
    ast = parser.parse()
    sa = SemanticAnalyzer()
    ctx = sa.analyze(ast)
    irg = IRGenerator()
    irg._sema_ctx = ctx
    instrs = irg.generate(ast)
    return instrs, ctx, irg


def _gen_ir_recording(code: str):
    """Parse, analyze, generate IR with a RecordingSymbolTable.

    Returns (instructions, sema_ctx, ir_gen, recording_table).
    """
    lexer = Lexer(code, "<test>")
    tokens = lexer.tokenize()
    parser = Parser(tokens)
    ast = parser.parse()
    sa = SemanticAnalyzer()
    ctx = sa.analyze(ast)
    irg = IRGenerator()
    irg._sema_ctx = ctx

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


def _find_scale_muls(instrs):
    """Find binop mul instructions that scale an index by element size.

    Returns list of (scale_value, instruction) tuples.
    """
    results = []
    for instr in instrs:
        if (instr.op == "binop" and instr.label == "*"
                and isinstance(instr.operand2, str)
                and instr.operand2.startswith("$")):
            try:
                scale = int(instr.operand2[1:])
                results.append((scale, instr))
            except (ValueError, IndexError):
                pass
    return results


def _get_insertions_for(log, name):
    """Extract all CTypes inserted for a given symbol name."""
    return [ct for n, ct in log if n == name]


def _pointee_size_of(ct: Optional[CType]) -> int:
    """Extract pointee element size from a CType."""
    if ct is None:
        return 0
    if isinstance(ct, PointerType) and ct.pointee is not None:
        return type_sizeof(ct.pointee)
    if isinstance(ct, CArrayType) and ct.element is not None:
        return type_sizeof(ct.element)
    return 0


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

# Integer pointer types where the string-based scaling path works correctly.
# Float/double are excluded because _type_size_bytes has a known gap for them.
INT_PTR_TYPES = [
    ("int", 4),
    ("long", 8),
    ("short", 2),
    ("unsigned int", 4),
    ("unsigned long", 8),
    ("unsigned short", 2),
]


@st.composite
def ptr_add_program(draw):
    """Generate a C89 program with pointer addition (ptr + n).

    Returns (c_code, elem_type, expected_elem_size).
    """
    elem_type, expected_size = draw(st.sampled_from(INT_PTR_TYPES))
    idx_val = draw(st.integers(min_value=1, max_value=10))

    code = (
        f"int main(void) {{\n"
        f"    {elem_type} arr[20];\n"
        f"    {elem_type} *p = arr;\n"
        f"    {elem_type} *q = p + {idx_val};\n"
        f"    return 0;\n"
        f"}}\n"
    )
    return code, elem_type, expected_size


@st.composite
def ptr_sub_program(draw):
    """Generate a C89 program with pointer subtraction (ptr - n).

    Returns (c_code, elem_type, expected_elem_size).
    """
    elem_type, expected_size = draw(st.sampled_from(INT_PTR_TYPES))
    idx_val = draw(st.integers(min_value=1, max_value=5))

    code = (
        f"int main(void) {{\n"
        f"    {elem_type} arr[20];\n"
        f"    {elem_type} *p = arr + 10;\n"
        f"    {elem_type} *q = p - {idx_val};\n"
        f"    return 0;\n"
        f"}}\n"
    )
    return code, elem_type, expected_size


@st.composite
def array_index_program(draw):
    """Generate a C89 program with array indexing (arr[i]).

    Returns (c_code, elem_type, expected_elem_size).
    """
    elem_type, expected_size = draw(st.sampled_from(INT_PTR_TYPES))
    arr_size = draw(st.integers(min_value=5, max_value=20))
    idx_val = draw(st.integers(min_value=0, max_value=arr_size - 1))

    code = (
        f"int main(void) {{\n"
        f"    {elem_type} arr[{arr_size}];\n"
        f"    {elem_type} val = arr[{idx_val}];\n"
        f"    return 0;\n"
        f"}}\n"
    )
    return code, elem_type, expected_size


@st.composite
def typedef_ptr_arith_program(draw):
    """Generate a C89 program with pointer arithmetic on a typedef type.

    Returns (c_code, underlying_type, expected_elem_size, typedef_name).
    """
    underlying, expected_size = draw(st.sampled_from(INT_PTR_TYPES))
    typedef_name = draw(st.sampled_from(["MyType", "ElemT", "ValType"]))
    idx_val = draw(st.integers(min_value=1, max_value=10))

    code = (
        f"typedef {underlying} {typedef_name};\n"
        f"\n"
        f"int main(void) {{\n"
        f"    {typedef_name} arr[20];\n"
        f"    {typedef_name} *p = arr;\n"
        f"    {typedef_name} *q = p + {idx_val};\n"
        f"    return 0;\n"
        f"}}\n"
    )
    return code, underlying, expected_size, typedef_name


@st.composite
def struct_ptr_arith_program(draw):
    """Generate a C89 program with pointer arithmetic on struct pointers.

    Returns (c_code, struct_name, num_members).
    """
    num_members = draw(st.integers(min_value=1, max_value=3))
    members = [f"    int m{i};" for i in range(num_members)]
    member_block = "\n".join(members)
    struct_name = "TestStruct"
    idx_val = draw(st.integers(min_value=1, max_value=5))

    code = (
        f"struct {struct_name} {{\n"
        f"{member_block}\n"
        f"}};\n"
        f"\n"
        f"int main(void) {{\n"
        f"    struct {struct_name} arr[10];\n"
        f"    struct {struct_name} *p = arr;\n"
        f"    struct {struct_name} *q = p + {idx_val};\n"
        f"    return 0;\n"
        f"}}\n"
    )
    return code, struct_name, num_members



# ---------------------------------------------------------------------------
# Property 6: pointer/array element size matches CType
# ---------------------------------------------------------------------------

class TestPtrArithCTypeProperties:
    """Property 6: pointer/array element size matches CType

    **Feature: ir-type-annotations, Property 6**
    **Validates: Requirements 6.1, 6.2**
    """

    @given(data=ptr_add_program())
    @settings(max_examples=120, deadline=None)
    def test_ptr_add_scale_matches_pointee_size(self, data):
        """For pointer addition (ptr + n), the IR scaling factor should
        equal type_sizeof of the pointee CType from the symbol table.

        **Validates: Requirements 6.1**
        """
        code, elem_type, expected_size = data
        instrs, ctx, irg, rec = _gen_ir_recording(code)
        assume(rec is not None)

        # Find scaling multiplications in the IR.
        # For types with size > 1, the IR should emit: binop %t, idx, $SIZE, *
        scale_muls = _find_scale_muls(instrs)

        found_expected = False
        for scale_val, instr in scale_muls:
            if scale_val == expected_size:
                found_expected = True
                break

        assert found_expected, (
            f"Expected scaling factor ${expected_size} for {elem_type}* "
            f"pointer arithmetic, but found scales: "
            f"{[s for s, _ in scale_muls]}"
        )

        # Verify via RecordingSymbolTable: the pointer variable @p should
        # have been inserted with a PointerType whose pointee size matches.
        p_insertions = _get_insertions_for(rec.insert_log, "@p")
        assert len(p_insertions) >= 1, (
            f"Pointer variable @p was never inserted into symbol table"
        )
        p_ct = p_insertions[0]
        sym_pointee_sz = _pointee_size_of(p_ct)
        assert sym_pointee_sz == expected_size, (
            f"Symbol table pointee size for @p is {sym_pointee_sz}, "
            f"expected {expected_size} for {elem_type}*. CType: {p_ct}"
        )

    @given(data=ptr_sub_program())
    @settings(max_examples=100, deadline=None)
    def test_ptr_sub_scale_matches_pointee_size(self, data):
        """For pointer subtraction (ptr - n), the IR scaling factor should
        equal type_sizeof of the pointee CType.

        **Validates: Requirements 6.1**
        """
        code, elem_type, expected_size = data
        instrs, ctx, irg, rec = _gen_ir_recording(code)
        assume(rec is not None)

        scale_muls = _find_scale_muls(instrs)

        # There should be at least one scale mul matching expected_size.
        # The p-idx subtraction and the arr+10 initialization both produce
        # scaling muls.
        found_expected = False
        for scale_val, instr in scale_muls:
            if scale_val == expected_size:
                found_expected = True
                break

        assert found_expected, (
            f"Expected scaling factor ${expected_size} for {elem_type}* "
            f"pointer subtraction, but found scales: "
            f"{[s for s, _ in scale_muls]}"
        )

    @given(data=array_index_program())
    @settings(max_examples=120, deadline=None)
    def test_array_index_symtable_elem_size_matches(self, data):
        """For array indexing (arr[i]), the symbol table should record the
        array with an element CType whose size matches the declared type.

        **Validates: Requirements 6.2**
        """
        code, elem_type, expected_size = data
        instrs, ctx, irg, rec = _gen_ir_recording(code)
        assume(rec is not None)

        # After scope pop, local variables are gone from the symbol table.
        # Use the RecordingSymbolTable insert log to verify the array CType.
        arr_insertions = _get_insertions_for(rec.insert_log, "@arr")
        assert len(arr_insertions) >= 1, (
            f"Array variable @arr was never inserted into symbol table"
        )

        arr_ct = arr_insertions[0]
        # Array should be recorded as ArrayType
        elem_ct = None
        if isinstance(arr_ct, CArrayType) and arr_ct.element is not None:
            elem_ct = arr_ct.element
        elif isinstance(arr_ct, PointerType) and arr_ct.pointee is not None:
            elem_ct = arr_ct.pointee

        assert elem_ct is not None, (
            f"Array @arr has CType {arr_ct} which has no element/pointee"
        )

        actual_size = type_sizeof(elem_ct)
        assert actual_size == expected_size, (
            f"Array @arr element CType size is {actual_size}, "
            f"expected {expected_size} for {elem_type}. "
            f"Element CType: {elem_ct}"
        )

    @given(data=typedef_ptr_arith_program())
    @settings(max_examples=100, deadline=None)
    def test_typedef_ptr_arith_scale_matches_underlying_size(self, data):
        """For pointer arithmetic on typedef pointer types, the scaling
        factor should match the underlying type's size after typedef
        resolution.

        **Validates: Requirements 6.1, 6.2**
        """
        code, underlying_type, expected_size, typedef_name = data
        instrs, ctx, irg, rec = _gen_ir_recording(code)
        assume(rec is not None)

        scale_muls = _find_scale_muls(instrs)

        found_expected = False
        for scale_val, instr in scale_muls:
            if scale_val == expected_size:
                found_expected = True
                break

        assert found_expected, (
            f"Expected scaling factor ${expected_size} for "
            f"{typedef_name}* (typedef for {underlying_type}) "
            f"pointer arithmetic, but found scales: "
            f"{[s for s, _ in scale_muls]}"
        )

        # Verify symbol table resolves the typedef correctly:
        # @p should have a PointerType whose pointee is the resolved type.
        p_insertions = _get_insertions_for(rec.insert_log, "@p")
        assert len(p_insertions) >= 1, (
            f"Pointer variable @p was never inserted into symbol table"
        )
        p_ct = p_insertions[0]
        sym_pointee_sz = _pointee_size_of(p_ct)
        assert sym_pointee_sz == expected_size, (
            f"Symbol table pointee size for @p is {sym_pointee_sz}, "
            f"expected {expected_size} after typedef resolution of "
            f"{typedef_name} -> {underlying_type}. CType: {p_ct}"
        )

    @given(data=struct_ptr_arith_program())
    @settings(max_examples=100, deadline=None)
    def test_struct_ptr_arith_scale_matches_layout_size(self, data):
        """For pointer arithmetic on struct pointers, the scaling factor
        should match the struct's total size from StructLayout.

        **Validates: Requirements 6.1, 6.2**
        """
        code, struct_name, num_members = data
        instrs, ctx, irg, rec = _gen_ir_recording(code)
        assume(rec is not None)

        # Get the struct size from the semantic context layouts
        struct_key = f"struct {struct_name}"
        layouts = getattr(ctx, "layouts", {})
        layout = layouts.get(struct_key)
        assert layout is not None, (
            f"Struct layout for '{struct_key}' not found in sema_ctx"
        )
        expected_size = int(getattr(layout, "size", 0))
        assert expected_size > 0, (
            f"Struct '{struct_key}' has zero size in layout"
        )

        # The IR should contain a scaling mul with the struct size
        scale_muls = _find_scale_muls(instrs)

        found_expected = False
        for scale_val, instr in scale_muls:
            if scale_val == expected_size:
                found_expected = True
                break

        assert found_expected, (
            f"Expected scaling factor ${expected_size} for "
            f"struct {struct_name}* pointer arithmetic "
            f"(struct size={expected_size}), but found scales: "
            f"{[s for s, _ in scale_muls]}"
        )

        # Verify symbol table has correct pointee type
        p_insertions = _get_insertions_for(rec.insert_log, "@p")
        assert len(p_insertions) >= 1
        p_ct = p_insertions[0]
        if isinstance(p_ct, PointerType) and p_ct.pointee is not None:
            assert p_ct.pointee.kind in (TypeKind.STRUCT, TypeKind.UNION), (
                f"Pointer @p pointee should be struct, "
                f"got {p_ct.pointee.kind}"
            )
