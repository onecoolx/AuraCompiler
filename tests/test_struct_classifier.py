"""Unit tests for the SysV ABI struct classifier (EightbyteClass / classify_struct / get_struct_pass_mode)."""

import pytest
from pycc.codegen import (
    EightbyteClass,
    classify_struct,
    get_struct_pass_mode,
    _classify_field,
    _merge_classes,
)
from pycc.semantics import StructLayout


# ---------------------------------------------------------------------------
# Helper to build a minimal StructLayout for testing
# ---------------------------------------------------------------------------

def _layout(kind, name, size, align, offsets, sizes, types):
    return StructLayout(
        kind=kind, name=name, size=size, align=align,
        member_offsets=offsets, member_sizes=sizes, member_types=types,
    )


# ---------------------------------------------------------------------------
# _classify_field
# ---------------------------------------------------------------------------

class TestClassifyField:
    def test_int(self):
        assert _classify_field("int") == EightbyteClass.INTEGER

    def test_char(self):
        assert _classify_field("char") == EightbyteClass.INTEGER

    def test_unsigned_int(self):
        assert _classify_field("unsigned int") == EightbyteClass.INTEGER

    def test_long(self):
        assert _classify_field("long") == EightbyteClass.INTEGER

    def test_pointer(self):
        assert _classify_field("int*") == EightbyteClass.INTEGER

    def test_enum(self):
        assert _classify_field("enum Color") == EightbyteClass.INTEGER

    def test_float(self):
        assert _classify_field("float") == EightbyteClass.SSE

    def test_double(self):
        assert _classify_field("double") == EightbyteClass.SSE

    def test_long_double(self):
        assert _classify_field("long double") == EightbyteClass.MEMORY


# ---------------------------------------------------------------------------
# _merge_classes
# ---------------------------------------------------------------------------

class TestMergeClasses:
    def test_memory_wins(self):
        assert _merge_classes(EightbyteClass.MEMORY, EightbyteClass.INTEGER) == EightbyteClass.MEMORY
        assert _merge_classes(EightbyteClass.SSE, EightbyteClass.MEMORY) == EightbyteClass.MEMORY

    def test_integer_over_sse(self):
        assert _merge_classes(EightbyteClass.INTEGER, EightbyteClass.SSE) == EightbyteClass.INTEGER
        assert _merge_classes(EightbyteClass.SSE, EightbyteClass.INTEGER) == EightbyteClass.INTEGER

    def test_sse_over_no_class(self):
        assert _merge_classes(EightbyteClass.SSE, EightbyteClass.NO_CLASS) == EightbyteClass.SSE

    def test_no_class_identity(self):
        assert _merge_classes(EightbyteClass.NO_CLASS, EightbyteClass.NO_CLASS) == EightbyteClass.NO_CLASS


# ---------------------------------------------------------------------------
# classify_struct
# ---------------------------------------------------------------------------

class TestClassifyStruct:
    def test_small_int_struct(self):
        """struct { int a; int b; } → 8 bytes, one eightbyte, INTEGER."""
        layout = _layout("struct", "S", 8, 4,
                         {"a": 0, "b": 4}, {"a": 4, "b": 4},
                         {"a": "int", "b": "int"})
        result = classify_struct("struct S", layout)
        assert result == [EightbyteClass.INTEGER]

    def test_two_eightbyte_int_struct(self):
        """struct { long a; long b; } → 16 bytes, two INTEGER eightbytes."""
        layout = _layout("struct", "S", 16, 8,
                         {"a": 0, "b": 8}, {"a": 8, "b": 8},
                         {"a": "long", "b": "long"})
        result = classify_struct("struct S", layout)
        assert result == [EightbyteClass.INTEGER, EightbyteClass.INTEGER]

    def test_large_struct_memory(self):
        """struct > 16 bytes → MEMORY."""
        layout = _layout("struct", "Big", 24, 8,
                         {"a": 0, "b": 8, "c": 16}, {"a": 8, "b": 8, "c": 8},
                         {"a": "long", "b": "long", "c": "long"})
        result = classify_struct("struct Big", layout)
        assert result == [EightbyteClass.MEMORY]

    def test_float_struct_sse(self):
        """struct { float a; float b; } → 8 bytes, one SSE eightbyte."""
        layout = _layout("struct", "F", 8, 4,
                         {"a": 0, "b": 4}, {"a": 4, "b": 4},
                         {"a": "float", "b": "float"})
        result = classify_struct("struct F", layout)
        assert result == [EightbyteClass.SSE]

    def test_double_struct_sse(self):
        """struct { double d; } → 8 bytes, one SSE eightbyte."""
        layout = _layout("struct", "D", 8, 8,
                         {"d": 0}, {"d": 8}, {"d": "double"})
        result = classify_struct("struct D", layout)
        assert result == [EightbyteClass.SSE]

    def test_mixed_int_float(self):
        """struct { int a; float b; } → 8 bytes, INTEGER wins over SSE."""
        layout = _layout("struct", "M", 8, 4,
                         {"a": 0, "b": 4}, {"a": 4, "b": 4},
                         {"a": "int", "b": "float"})
        result = classify_struct("struct M", layout)
        assert result == [EightbyteClass.INTEGER]

    def test_two_eightbyte_mixed(self):
        """struct { int a; int b; double c; } → 16 bytes, [INTEGER, SSE]."""
        layout = _layout("struct", "Mix", 16, 8,
                         {"a": 0, "b": 4, "c": 8},
                         {"a": 4, "b": 4, "c": 8},
                         {"a": "int", "b": "int", "c": "double"})
        result = classify_struct("struct Mix", layout)
        assert result == [EightbyteClass.INTEGER, EightbyteClass.SSE]

    def test_long_double_member_memory(self):
        """struct with long double member → MEMORY."""
        layout = _layout("struct", "LD", 16, 16,
                         {"ld": 0}, {"ld": 16}, {"ld": "long double"})
        result = classify_struct("struct LD", layout)
        assert result == [EightbyteClass.MEMORY]

    def test_pointer_member_integer(self):
        """struct { int* p; } → 8 bytes, INTEGER."""
        layout = _layout("struct", "P", 8, 8,
                         {"p": 0}, {"p": 8}, {"p": "int*"})
        result = classify_struct("struct P", layout)
        assert result == [EightbyteClass.INTEGER]

    def test_char_struct(self):
        """struct { char c; } → 1 byte (padded to 1), INTEGER."""
        layout = _layout("struct", "C", 1, 1,
                         {"c": 0}, {"c": 1}, {"c": "char"})
        result = classify_struct("struct C", layout)
        assert result == [EightbyteClass.INTEGER]

    def test_empty_struct(self):
        """Empty struct (size 0) → NO_CLASS."""
        layout = _layout("struct", "E", 0, 1, {}, {}, {})
        result = classify_struct("struct E", layout)
        assert result == [EightbyteClass.NO_CLASS]

    def test_union_classification(self):
        """union { int a; double b; } → 8 bytes, INTEGER (int wins over double)."""
        layout = _layout("union", "U", 8, 8,
                         {"a": 0, "b": 0}, {"a": 4, "b": 8},
                         {"a": "int", "b": "double"})
        result = classify_struct("union U", layout)
        assert result == [EightbyteClass.INTEGER]


# ---------------------------------------------------------------------------
# get_struct_pass_mode
# ---------------------------------------------------------------------------

class TestGetStructPassMode:
    def test_integer_registers(self):
        assert get_struct_pass_mode([EightbyteClass.INTEGER]) == "registers"

    def test_sse_registers(self):
        assert get_struct_pass_mode([EightbyteClass.SSE]) == "registers"

    def test_mixed_registers(self):
        assert get_struct_pass_mode([EightbyteClass.INTEGER, EightbyteClass.SSE]) == "registers"

    def test_memory_hidden_ptr(self):
        assert get_struct_pass_mode([EightbyteClass.MEMORY]) == "hidden_ptr"

    def test_empty_classification_stack(self):
        assert get_struct_pass_mode([]) == "stack"

    def test_no_class_registers(self):
        """NO_CLASS alone → registers (degenerate case)."""
        assert get_struct_pass_mode([EightbyteClass.NO_CLASS]) == "registers"
