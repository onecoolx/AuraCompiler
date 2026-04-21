"""Property-based tests for cast expression type safety.

**Feature: ir-type-annotations, Property 5: Cast creates new temp without overwriting source type**

**Validates: Requirements 5.1**

For any C89 program containing cast expressions, after IR generation, the cast
source operand's CType in the TypedSymbolTable should remain exactly the same as
before the cast -- casts should only create new temporary variables, never modify
existing symbols' types.

Testing approach: use Hypothesis to generate random C89 programs with cast
expressions between different types, compile through the IR generator with a
RecordingSymbolTable that logs all insert() calls.  After IR generation we verify:
  1. Named variables (@name) are never re-inserted with a different CType by cast
  2. Cast conversion instructions always produce new temp variables (%tN)
  3. The cast result is distinct from the source operand
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from pycc.lexer import Lexer
from pycc.parser import Parser
from pycc.semantics import SemanticAnalyzer
from pycc.ir import IRGenerator
from pycc.types import (
    CType, TypeKind, IntegerType, FloatType, PointerType,
    StructType as CStructType, TypedSymbolTable,
    ast_type_to_ctype_resolved, ctype_to_ir_type,
)


# ---------------------------------------------------------------------------
# Recording wrapper for TypedSymbolTable
# ---------------------------------------------------------------------------

class RecordingSymbolTable(TypedSymbolTable):
    """TypedSymbolTable subclass that records every insert() call.

    After IR generation (even after scope pop), we can inspect the log to
    verify that named variables were never re-inserted with a different CType.
    """

    def __init__(self, sema_ctx=None):
        super().__init__(sema_ctx)
        # Each entry: (name, resolved_ctype) captured at insert time
        self.insert_log: List[Tuple[str, CType]] = []

    def insert(self, name: str, ctype: CType) -> None:
        """Insert and record the resolved CType."""
        resolved = self._resolve_typedef(ctype)
        self.insert_log.append((name, resolved))
        super().insert(name, ctype)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _gen_ir_recording(code: str):
    """Parse, analyze, generate IR with a RecordingSymbolTable.

    Returns (instructions, sema_ctx, ir_gen, recording_table).
    The recording_table contains the full insert log even after scope pop.
    """
    lexer = Lexer(code, "<test>")
    tokens = lexer.tokenize()
    parser = Parser(tokens)
    ast = parser.parse()
    sa = SemanticAnalyzer()
    ctx = sa.analyze(ast)
    irg = IRGenerator()
    irg._sema_ctx = ctx

    # Inject our recording table.  generate() will overwrite _sym_table,
    # so we patch the TypedSymbolTable class temporarily.
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


def _ctypes_match(a: Optional[CType], b: Optional[CType]) -> bool:
    """Check if two CTypes are semantically equivalent (ignoring qualifiers)."""
    if a is None or b is None:
        return a is b
    if a.kind != b.kind:
        return False
    if isinstance(a, PointerType) and isinstance(b, PointerType):
        return _ctypes_match(a.pointee, b.pointee)
    if isinstance(a, CStructType) and isinstance(b, CStructType):
        return a.tag == b.tag
    if isinstance(a, IntegerType) and isinstance(b, IntegerType):
        return a.is_unsigned == b.is_unsigned
    if isinstance(a, FloatType) and isinstance(b, FloatType):
        return True
    return True


def _get_named_var_insertions(log: List[Tuple[str, CType]], var_name: str
                               ) -> List[CType]:
    """Extract all CTypes inserted for a named variable from the log."""
    return [ct for name, ct in log if name == var_name]


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

# Integer source types: (C declaration, variable name)
INT_SOURCES = [
    ("int", "x"),
    ("long", "l"),
    ("unsigned int", "u"),
    ("unsigned long", "ul"),
]

# Float source types
FLOAT_SOURCES = [
    ("float", "f"),
    ("double", "d"),
]

ALL_SOURCES = INT_SOURCES + FLOAT_SOURCES

# Cast destination types (non-pointer scalars)
SCALAR_DSTS = [
    "char", "unsigned char", "short", "unsigned short",
    "int", "unsigned int", "long", "unsigned long",
    "float", "double",
]

# Pointer cast destinations
PTR_DSTS = ["void *", "char *", "int *"]


def _normalize(s: str) -> str:
    """Normalize a type string for comparison."""
    s = " ".join(s.strip().lower().split())
    for old, new in [("short int", "short"), ("long int", "long"),
                     ("signed int", "int"), ("signed char", "char"),
                     ("signed short", "short"), ("signed long", "long")]:
        if s == old:
            s = new
    return s


@st.composite
def scalar_cast_program(draw):
    """Generate a C89 program casting a scalar variable to another scalar type.

    Returns (c_code, var_name, ir_var_name, src_type, dst_type).
    """
    src_type, var_name = draw(st.sampled_from(ALL_SOURCES))
    dst_type = draw(st.sampled_from(SCALAR_DSTS))
    assume(_normalize(dst_type) != _normalize(src_type))

    # Float-to-pointer is invalid; skip
    is_src_fp = src_type in ("float", "double")
    is_dst_ptr = "*" in dst_type
    assume(not (is_src_fp and is_dst_ptr))

    init = "1.5" if is_src_fp else "42"
    code = f"""
int main(void) {{
    {src_type} {var_name} = {init};
    {dst_type} result = ({dst_type}){var_name};
    return 0;
}}
"""
    return code, var_name, f"@{var_name}", src_type, dst_type


@st.composite
def ptr_cast_program(draw):
    """Generate a C89 program casting an integer to a pointer type."""
    src_type, var_name = draw(st.sampled_from(INT_SOURCES))
    dst_type = draw(st.sampled_from(PTR_DSTS))

    code = f"""
int main(void) {{
    {src_type} {var_name} = 0;
    {dst_type} result = ({dst_type}){var_name};
    return 0;
}}
"""
    return code, var_name, f"@{var_name}", src_type, dst_type


@st.composite
def typedef_cast_program(draw):
    """Generate a C89 program casting to a typedef target."""
    src_type, var_name = draw(st.sampled_from(INT_SOURCES))
    typedef_name, underlying = draw(st.sampled_from([
        ("MyInt", "int"),
        ("MyLong", "long"),
        ("MyChar", "char"),
        ("MyUInt", "unsigned int"),
    ]))
    assume(_normalize(underlying) != _normalize(src_type))

    code = f"""
typedef {underlying} {typedef_name};

int main(void) {{
    {src_type} {var_name} = 0;
    {typedef_name} result = ({typedef_name}){var_name};
    return 0;
}}
"""
    return code, var_name, f"@{var_name}", src_type, typedef_name


@st.composite
def multi_cast_program(draw):
    """Generate a C89 program with multiple casts on the same variable."""
    src_type, var_name = draw(st.sampled_from(INT_SOURCES))
    num = draw(st.integers(min_value=2, max_value=3))
    int_dsts = ["char", "short", "long", "unsigned int",
                "unsigned char", "unsigned short"]
    dsts = draw(st.lists(st.sampled_from(int_dsts), min_size=num, max_size=num))
    assume(any(_normalize(d) != _normalize(src_type) for d in dsts))

    lines = [f"    {d} r{i} = ({d}){var_name};" for i, d in enumerate(dsts)]
    body = "\n".join(lines)
    code = f"""
int main(void) {{
    {src_type} {var_name} = 42;
{body}
    return 0;
}}
"""
    return code, var_name, f"@{var_name}", src_type, dsts


# ---------------------------------------------------------------------------
# Property 5: Cast creates new temp without overwriting source type
# ---------------------------------------------------------------------------

class TestCastCTypeProperties:
    """Property 5: Cast creates new temp without overwriting source type

    **Feature: ir-type-annotations, Property 5**
    **Validates: Requirements 5.1**
    """

    @given(data=scalar_cast_program())
    @settings(max_examples=120, deadline=None)
    def test_scalar_cast_does_not_reinsert_source_in_symtable(self, data):
        """For any scalar-to-scalar cast, the source variable should be
        inserted into the TypedSymbolTable exactly once (at declaration).
        The cast must NOT re-insert the source variable with a different CType.

        **Validates: Requirements 5.1**
        """
        code, var_name, ir_var, src_type, dst_type = data
        instrs, ctx, irg, rec = _gen_ir_recording(code)
        assume(rec is not None)

        insertions = _get_named_var_insertions(rec.insert_log, ir_var)
        assert len(insertions) >= 1, (
            f"Source variable {ir_var} was never inserted into symbol table"
        )

        # The first insertion is the declaration.  Any subsequent insertion
        # with a DIFFERENT CType means the cast clobbered the source.
        first_ct = insertions[0]
        for i, ct in enumerate(insertions[1:], 1):
            assert _ctypes_match(ct, first_ct), (
                f"Cast ({dst_type}){var_name} re-inserted {ir_var} into "
                f"TypedSymbolTable with different CType at insertion #{i}: "
                f"got {ct}, original was {first_ct}"
            )

    @given(data=ptr_cast_program())
    @settings(max_examples=100, deadline=None)
    def test_ptr_cast_does_not_reinsert_source_in_symtable(self, data):
        """For any integer-to-pointer cast, the source variable should not
        be re-inserted into the TypedSymbolTable with a pointer CType.

        **Validates: Requirements 5.1**
        """
        code, var_name, ir_var, src_type, dst_type = data
        instrs, ctx, irg, rec = _gen_ir_recording(code)
        assume(rec is not None)

        insertions = _get_named_var_insertions(rec.insert_log, ir_var)
        assert len(insertions) >= 1

        first_ct = insertions[0]
        for i, ct in enumerate(insertions[1:], 1):
            assert _ctypes_match(ct, first_ct), (
                f"Cast ({dst_type}){var_name} re-inserted {ir_var} into "
                f"TypedSymbolTable with CType {ct}, original was {first_ct}"
            )

    @given(data=typedef_cast_program())
    @settings(max_examples=100, deadline=None)
    def test_typedef_cast_does_not_reinsert_source_in_symtable(self, data):
        """For any cast to a typedef target, the source variable should not
        be re-inserted into the TypedSymbolTable.

        **Validates: Requirements 5.1**
        """
        code, var_name, ir_var, src_type, typedef_name = data
        instrs, ctx, irg, rec = _gen_ir_recording(code)
        assume(rec is not None)

        insertions = _get_named_var_insertions(rec.insert_log, ir_var)
        assert len(insertions) >= 1

        first_ct = insertions[0]
        for i, ct in enumerate(insertions[1:], 1):
            assert _ctypes_match(ct, first_ct), (
                f"Typedef cast ({typedef_name}){var_name} re-inserted "
                f"{ir_var} with CType {ct}, original was {first_ct}"
            )

    @given(data=multi_cast_program())
    @settings(max_examples=100, deadline=None)
    def test_multi_cast_does_not_reinsert_source_in_symtable(self, data):
        """For multiple casts on the same variable, the source should be
        inserted into the TypedSymbolTable exactly once.

        **Validates: Requirements 5.1**
        """
        code, var_name, ir_var, src_type, dst_types = data
        instrs, ctx, irg, rec = _gen_ir_recording(code)
        assume(rec is not None)

        insertions = _get_named_var_insertions(rec.insert_log, ir_var)
        assert len(insertions) >= 1

        first_ct = insertions[0]
        for i, ct in enumerate(insertions[1:], 1):
            assert _ctypes_match(ct, first_ct), (
                f"Multiple casts on {var_name} re-inserted {ir_var} with "
                f"CType {ct} at insertion #{i}, original was {first_ct}"
            )

    @given(data=scalar_cast_program())
    @settings(max_examples=120, deadline=None)
    def test_cast_conversion_uses_new_temp(self, data):
        """For any cast that produces a conversion instruction, the result
        should be a new temporary variable (%tN), not the source variable.

        **Validates: Requirements 5.1**
        """
        code, var_name, ir_var, src_type, dst_type = data
        instrs, ctx, irg, _ = _gen_ir_recording(code)

        # IR ops that represent explicit type conversions
        conv_ops = {"i2f", "i2d", "i2ld", "f2i", "d2i", "ld2i",
                    "f2d", "d2f", "f2ld", "d2ld", "ld2f", "ld2d",
                    "sext8", "sext16"}

        for instr in instrs:
            if instr.op in conv_ops and instr.operand1 == ir_var:
                assert instr.result is not None, (
                    f"Conversion {instr.op} has no result"
                )
                assert instr.result.startswith("%t"), (
                    f"Conversion {instr.op} result '{instr.result}' "
                    f"is not a temp variable"
                )
                assert instr.result != ir_var, (
                    f"Conversion {instr.op} overwrites source {ir_var}"
                )

            # Truncation via bitwise AND (char/short casts)
            if (instr.op == "binop" and instr.label == "&"
                    and instr.operand1 == ir_var
                    and instr.operand2 in ("$255", "$65535")):
                assert instr.result is not None
                assert instr.result.startswith("%t"), (
                    f"Truncation result '{instr.result}' is not a temp"
                )
                assert instr.result != ir_var, (
                    f"Truncation overwrites source {ir_var}"
                )

    @given(data=scalar_cast_program())
    @settings(max_examples=120, deadline=None)
    def test_cast_result_type_is_destination_type(self, data):
        """For any cast conversion instruction, the result_type should
        reflect the cast destination type, not the source type.

        **Validates: Requirements 5.1**
        """
        code, var_name, ir_var, src_type, dst_type = data
        instrs, ctx, irg, rec = _gen_ir_recording(code)
        assume(rec is not None)

        conv_ops = {"i2f", "i2d", "i2ld", "f2i", "d2i", "ld2i",
                    "f2d", "d2f", "f2ld", "d2ld", "ld2f", "ld2d",
                    "sext8", "sext16"}

        for instr in instrs:
            if instr.op in conv_ops and instr.operand1 == ir_var:
                if instr.result_type is not None:
                    # The result_type should be the destination type
                    expected = ast_type_to_ctype_resolved(dst_type, ctx)
                    assert _ctypes_match(instr.result_type, expected), (
                        f"Conversion {instr.op} result_type={instr.result_type}"
                        f" doesn't match destination type {expected}"
                    )
