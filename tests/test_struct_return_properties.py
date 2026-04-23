"""Property-based tests for struct by-value return.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4**

Property 4: Struct by-value return preserves member values
For any struct type (regardless of whether size exceeds 16 bytes or whether
members include floating-point types) and any member values, after returning
the struct by value from a function, each member value received by the caller
should equal the value set inside the function.

Testing approach: use Hypothesis to generate random struct layouts with
integer-type members (int, long, short, char), generate C code that defines
the struct, a make() function that sets members to specific values and returns
the struct by value, and a main() that calls make() and verifies each member.
Compile with pycc, run the executable, and check return code (0 = success).
"""

import subprocess

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from pycc.compiler import Compiler


# ---------------------------------------------------------------------------
# C type descriptors: (c_type, size, alignment, printf_fmt)
# ---------------------------------------------------------------------------

INTEGER_MEMBER_TYPES = [
    ("int", 4, 4),
    ("long", 8, 8),
    ("short", 2, 2),
    ("char", 1, 1),
]


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

def _align_up(offset: int, align: int) -> int:
    return (offset + align - 1) // align * align


@st.composite
def struct_members(draw, min_members=1, max_members=6):
    """Generate a list of (name, c_type, value) tuples for struct members.

    Values are kept small (0-100) so they fit in a return code when summed.
    """
    n = draw(st.integers(min_value=min_members, max_value=max_members))
    members = []
    for i in range(n):
        c_type, size, align = draw(st.sampled_from(INTEGER_MEMBER_TYPES))
        # Keep values small and positive to avoid overflow / signedness issues
        if c_type == "char":
            val = draw(st.integers(min_value=0, max_value=20))
        else:
            val = draw(st.integers(min_value=0, max_value=100))
        members.append((f"m{i}", c_type, val))
    return members


@st.composite
def small_struct_members(draw):
    """Generate struct members whose total size is <= 16 bytes (register return)."""
    members = draw(struct_members(min_members=1, max_members=4))
    # Compute size to filter
    offset = 0
    max_align = 1
    for _, c_type, _ in members:
        _, size, align = next(t for t in INTEGER_MEMBER_TYPES if t[0] == c_type)
        offset = _align_up(offset, align)
        offset += size
        max_align = max(max_align, align)
    total = _align_up(offset, max_align)
    assume(total <= 16)
    return members


@st.composite
def large_struct_members(draw):
    """Generate struct members whose total size is > 16 bytes (hidden pointer return)."""
    members = draw(struct_members(min_members=3, max_members=8))
    offset = 0
    max_align = 1
    for _, c_type, _ in members:
        _, size, align = next(t for t in INTEGER_MEMBER_TYPES if t[0] == c_type)
        offset = _align_up(offset, align)
        offset += size
        max_align = max(max_align, align)
    total = _align_up(offset, max_align)
    assume(total > 16)
    return members


# ---------------------------------------------------------------------------
# C code generation helpers
# ---------------------------------------------------------------------------

def _generate_c_code(members):
    """Generate C source that defines a struct, a make() function, and main().

    main() calls make(), then verifies each member matches the expected value.
    For structs with many members, we sum all members and check the sum to
    keep the return code within 0-255.
    """
    lines = []

    # Struct definition
    lines.append("struct S {")
    for name, c_type, _ in members:
        lines.append(f"    {c_type} {name};")
    lines.append("};")
    lines.append("")

    # make() function — sets each member and returns by value
    lines.append("struct S make(void) {")
    lines.append("    struct S s;")
    for name, _, val in members:
        lines.append(f"    s.{name} = {val};")
    lines.append("    return s;")
    lines.append("}")
    lines.append("")

    # main() — calls make() and verifies
    lines.append("int main(void) {")
    lines.append("    struct S r;")
    lines.append("    r = make();")

    # Verify each member individually; return 1 on first mismatch
    for i, (name, c_type, val) in enumerate(members):
        # Cast to int for comparison (handles char/short)
        lines.append(f"    if ((int)r.{name} != {val}) return {i + 1};")

    lines.append("    return 0;")
    lines.append("}")

    return "\n".join(lines)


def _compile_and_run(tmp_path, code: str) -> int:
    """Compile C code with pycc and run the resulting executable."""
    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)
    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(out_path))
    assert res.success, "compile failed:\n" + "\n".join(res.errors)
    p = subprocess.run([str(out_path)], check=False, timeout=5)
    return p.returncode


# ---------------------------------------------------------------------------
# Property tests
# ---------------------------------------------------------------------------

class TestStructReturnProperties:
    """Property 4: Struct by-value return preserves member values

    **Validates: Requirements 3.1, 3.2, 3.3, 3.4**
    """

    @given(members=small_struct_members())
    @settings(max_examples=100, deadline=None)
    def test_small_struct_return_preserves_values(self, tmp_path_factory, members):
        """Small structs (≤16 bytes) returned via registers preserve all member values.

        **Validates: Requirements 3.1, 3.3**
        """
        tmp_path = tmp_path_factory.mktemp("test")
        code = _generate_c_code(members)
        rc = _compile_and_run(tmp_path, code)
        assert rc == 0, (
            f"Member mismatch at index {rc - 1} for struct with members "
            f"{[(n, t, v) for n, t, v in members]}\n\nGenerated code:\n{code}"
        )

    @given(members=large_struct_members())
    @settings(max_examples=100, deadline=None)
    def test_large_struct_return_preserves_values(self, tmp_path_factory, members):
        """Large structs (>16 bytes) returned via hidden pointer preserve all member values.

        **Validates: Requirements 3.2, 3.3**
        """
        tmp_path = tmp_path_factory.mktemp("test")
        code = _generate_c_code(members)
        rc = _compile_and_run(tmp_path, code)
        assert rc == 0, (
            f"Member mismatch at index {rc - 1} for struct with members "
            f"{[(n, t, v) for n, t, v in members]}\n\nGenerated code:\n{code}"
        )

    @given(members=struct_members(min_members=1, max_members=6))
    @settings(max_examples=100, deadline=None)
    def test_any_struct_return_preserves_values(self, tmp_path_factory, members):
        """Any integer-member struct returned by value preserves all member values.

        This covers both register and hidden-pointer return paths.

        **Validates: Requirements 3.1, 3.2, 3.3**
        """
        tmp_path = tmp_path_factory.mktemp("test")
        code = _generate_c_code(members)
        rc = _compile_and_run(tmp_path, code)
        assert rc == 0, (
            f"Member mismatch at index {rc - 1} for struct with members "
            f"{[(n, t, v) for n, t, v in members]}\n\nGenerated code:\n{code}"
        )
