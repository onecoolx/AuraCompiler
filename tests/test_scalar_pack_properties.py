"""Property-based tests for scalar packing round-trip consistency.

**Validates: Requirements 2.4**

Property 2: 标量打包往返一致性
对于任意支持的标量类型和该类型范围内的任意值，将值打包为字节序列后再按相同格式解包，
应得到原始值（整数截断到类型宽度后）。
"""
import struct

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from pycc.ir import IRGenerator, ResolvedType, InitFragment
from pycc.ast_nodes import IntLiteral, FloatLiteral

# Default line/column for test AST nodes
L, C = 0, 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ir_gen():
    """Create a minimal IRGenerator for testing scalar fragment collection."""
    gen = IRGenerator()
    gen._sema_ctx = None
    gen._enum_constants = {}
    gen._fn_name = "test_fn"
    return gen


def _scalar(name, size, fmt, mask, is_float=False):
    return ResolvedType(
        kind="scalar", name=name, size=size,
        pack_format=fmt, pack_mask=mask, is_float=is_float
    )


# ---------------------------------------------------------------------------
# Scalar type definitions with value ranges
# ---------------------------------------------------------------------------

# Integer types: (name, size, pack_format, mask, min_val, max_val)
INTEGER_TYPES = [
    ("char",              1, "<B", 0xFF,               0, 0xFF),
    ("signed char",       1, "<B", 0xFF,               0, 0xFF),
    ("unsigned char",     1, "<B", 0xFF,               0, 0xFF),
    ("short",             2, "<H", 0xFFFF,             0, 0xFFFF),
    ("unsigned short",    2, "<H", 0xFFFF,             0, 0xFFFF),
    ("int",              4, "<I", 0xFFFFFFFF,          0, 0xFFFFFFFF),
    ("unsigned int",     4, "<I", 0xFFFFFFFF,          0, 0xFFFFFFFF),
    ("long",             8, "<Q", 0xFFFFFFFFFFFFFFFF,  0, 0xFFFFFFFFFFFFFFFF),
    ("unsigned long",    8, "<Q", 0xFFFFFFFFFFFFFFFF,  0, 0xFFFFFFFFFFFFFFFF),
    ("long long",        8, "<Q", 0xFFFFFFFFFFFFFFFF,  0, 0xFFFFFFFFFFFFFFFF),
    ("unsigned long long", 8, "<Q", 0xFFFFFFFFFFFFFFFF, 0, 0xFFFFFFFFFFFFFFFF),
    ("_Bool",            1, "<B", 0x1,                 0, 1),
]

# Float types: (name, size, pack_format)
FLOAT_TYPES = [
    ("float",  4, "<f"),
    ("double", 8, "<d"),
]


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

@st.composite
def integer_type_and_value(draw):
    """Generate a random integer type and a value within its range."""
    type_info = draw(st.sampled_from(INTEGER_TYPES))
    name, size, fmt, mask, min_val, max_val = type_info
    # Generate any integer, then mask it (simulates C truncation behavior)
    value = draw(st.integers(min_value=min_val, max_value=max_val))
    return (name, size, fmt, mask, value)


@st.composite
def signed_integer_type_and_value(draw):
    """Generate a random integer type with a negative value (tests masking)."""
    type_info = draw(st.sampled_from(INTEGER_TYPES))
    name, size, fmt, mask, min_val, max_val = type_info
    # Generate a negative value that will be masked to type width
    value = draw(st.integers(min_value=-2**31, max_value=-1))
    return (name, size, fmt, mask, value)


@st.composite
def float_type_and_value(draw):
    """Generate a random float type and a finite float value."""
    type_info = draw(st.sampled_from(FLOAT_TYPES))
    name, size, fmt = type_info
    if name == "float":
        # Use float32-representable values to avoid precision issues
        value = draw(st.floats(
            min_value=-3.4e38, max_value=3.4e38,
            allow_nan=False, allow_infinity=False,
            allow_subnormal=False,
        ))
    else:
        value = draw(st.floats(
            allow_nan=False, allow_infinity=False,
            allow_subnormal=False,
        ))
    return (name, size, fmt, value)


# ---------------------------------------------------------------------------
# Property tests
# ---------------------------------------------------------------------------

class TestScalarPackRoundTrip:
    """Property 2: 标量打包往返一致性

    **Validates: Requirements 2.4**
    """

    @given(data=integer_type_and_value())
    @settings(max_examples=100)
    def test_integer_pack_roundtrip(self, data):
        """For any integer type and value in range, pack then unpack yields original."""
        name, size, fmt, mask, value = data
        rtype = _scalar(name, size, fmt, mask, is_float=False)
        gen = _make_ir_gen()

        expr = IntLiteral(line=L, column=C, value=value)
        frags = gen._collect_scalar_fragment(rtype, expr, 0)

        assert frags is not None, f"Failed to pack {name} value {value}"
        assert len(frags) == 1
        frag = frags[0]

        assert frag.kind == "int"
        assert frag.size == size
        assert frag.offset == 0

        # Unpack and verify round-trip
        unpacked = struct.unpack(fmt, frag.value)[0]
        expected = value & mask
        assert unpacked == expected, (
            f"Round-trip failed for {name}: packed {value} & {hex(mask)} = "
            f"{expected}, but unpacked {unpacked}"
        )

    @given(data=signed_integer_type_and_value())
    @settings(max_examples=100)
    def test_negative_integer_pack_roundtrip(self, data):
        """For any integer type with negative value, masking and pack/unpack is consistent."""
        name, size, fmt, mask, value = data
        rtype = _scalar(name, size, fmt, mask, is_float=False)
        gen = _make_ir_gen()

        expr = IntLiteral(line=L, column=C, value=value)
        frags = gen._collect_scalar_fragment(rtype, expr, 0)

        assert frags is not None, f"Failed to pack {name} value {value}"
        assert len(frags) == 1
        frag = frags[0]

        assert frag.kind == "int"
        assert frag.size == size

        # Unpack and verify: value is masked to type width
        unpacked = struct.unpack(fmt, frag.value)[0]
        expected = value & mask
        assert unpacked == expected, (
            f"Round-trip failed for {name}: {value} & {hex(mask)} = "
            f"{expected}, but unpacked {unpacked}"
        )

    @given(data=float_type_and_value())
    @settings(max_examples=100)
    def test_float_pack_roundtrip(self, data):
        """For any float type and finite value, pack then unpack yields original."""
        name, size, fmt, value = data
        rtype = _scalar(name, size, fmt, None, is_float=True)
        gen = _make_ir_gen()

        expr = FloatLiteral(line=L, column=C, value=value)
        frags = gen._collect_scalar_fragment(rtype, expr, 0)

        assert frags is not None, f"Failed to pack {name} value {value}"
        assert len(frags) == 1
        frag = frags[0]

        assert frag.kind == "float"
        assert frag.size == size
        assert frag.offset == 0

        # Unpack and verify round-trip
        unpacked = struct.unpack(fmt, frag.value)[0]

        if name == "float":
            # float32 has limited precision; pack/unpack should be exact
            # because we pack the value and unpack with same format
            expected = struct.unpack("<f", struct.pack("<f", value))[0]
            assert unpacked == expected, (
                f"Float round-trip failed: packed {value}, "
                f"expected {expected}, got {unpacked}"
            )
        else:
            # double: exact round-trip for finite values
            assert unpacked == value, (
                f"Double round-trip failed: packed {value}, got {unpacked}"
            )

    @given(data=integer_type_and_value())
    @settings(max_examples=100)
    def test_integer_fragment_size_matches_type(self, data):
        """The packed fragment size always matches the declared type size."""
        name, size, fmt, mask, value = data
        rtype = _scalar(name, size, fmt, mask, is_float=False)
        gen = _make_ir_gen()

        expr = IntLiteral(line=L, column=C, value=value)
        frags = gen._collect_scalar_fragment(rtype, expr, 0)

        assert frags is not None
        assert len(frags[0].value) == size, (
            f"Packed bytes length {len(frags[0].value)} != type size {size} for {name}"
        )

    @given(data=float_type_and_value())
    @settings(max_examples=100)
    def test_float_fragment_size_matches_type(self, data):
        """The packed float fragment size always matches the declared type size."""
        name, size, fmt, value = data
        rtype = _scalar(name, size, fmt, None, is_float=True)
        gen = _make_ir_gen()

        expr = FloatLiteral(line=L, column=C, value=value)
        frags = gen._collect_scalar_fragment(rtype, expr, 0)

        assert frags is not None
        assert len(frags[0].value) == size, (
            f"Packed bytes length {len(frags[0].value)} != type size {size} for {name}"
        )
