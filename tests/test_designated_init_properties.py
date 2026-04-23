"""Property-based tests for designated initializer correctness.

**Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5, 5.6**

Property 6: Struct designated initializer correctness
For any struct type and any subset of members with designated initialization values,
after initialization with designated initializers, designated members should have
the specified values and undesignated members should be zero.

Property 7: Array designated initializer correctness
For any array size and any subset of indices with designated initialization values,
after initialization with designated initializers, designated elements should have
the specified values and undesignated elements should be zero.

Property 8: Invalid designated initializer rejection
For any invalid member name (not in the struct definition) or out-of-bounds array index,
the compiler should produce a compilation error rather than silently accepting it.

Testing approach: use Hypothesis to generate random struct/array layouts and
designated initialization values, compile with pycc, run the executable, and
check return code (0 = success). For invalid cases, verify compilation fails.
"""

import subprocess

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from pycc.compiler import Compiler


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

@st.composite
def struct_layout_and_designated_values(draw):
    """Generate a struct with 2-5 int members and a random subset designated
    with values in 0-100.

    Returns (members, designated) where:
      members: list of member names, e.g. ["m0", "m1", "m2"]
      designated: dict mapping member name -> value for the designated subset
    """
    n = draw(st.integers(min_value=2, max_value=5))
    members = [f"m{i}" for i in range(n)]
    # Pick a non-empty subset of members to designate
    subset_size = draw(st.integers(min_value=1, max_value=n))
    chosen = draw(
        st.lists(
            st.sampled_from(members),
            min_size=subset_size,
            max_size=subset_size,
            unique=True,
        )
    )
    designated = {}
    for name in chosen:
        designated[name] = draw(st.integers(min_value=0, max_value=100))
    return members, designated


@st.composite
def array_layout_and_designated_values(draw):
    """Generate an array of size 2-8 and a random subset of indices designated
    with values in 0-100.

    Returns (size, designated) where:
      size: int array size
      designated: dict mapping index -> value for the designated subset
    """
    size = draw(st.integers(min_value=2, max_value=8))
    indices = list(range(size))
    subset_size = draw(st.integers(min_value=1, max_value=size))
    chosen = draw(
        st.lists(
            st.sampled_from(indices),
            min_size=subset_size,
            max_size=subset_size,
            unique=True,
        )
    )
    designated = {}
    for idx in chosen:
        designated[idx] = draw(st.integers(min_value=0, max_value=100))
    return size, designated


# Strategy for invalid struct member names
invalid_member_names = st.text(
    alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyz"),
    min_size=3,
    max_size=8,
).filter(lambda s: not s.startswith("m"))  # Ensure it doesn't match m0, m1, ...


# Strategy for out-of-bounds array indices
@st.composite
def oob_array_index(draw):
    """Generate an array size and an out-of-bounds index."""
    size = draw(st.integers(min_value=2, max_value=8))
    # Index is >= size (out of bounds)
    index = draw(st.integers(min_value=size, max_value=size + 50))
    return size, index


# ---------------------------------------------------------------------------
# C code generation helpers
# ---------------------------------------------------------------------------

def _generate_struct_designated_init_code(members, designated):
    """Generate C code that initializes a struct with designated initializers
    and verifies all members.

    Returns 0 on success, non-zero on first mismatch.
    """
    lines = []
    lines.append("struct S {")
    for name in members:
        lines.append(f"    int {name};")
    lines.append("};")
    lines.append("")
    lines.append("int main(void) {")

    # Build designated initializer list
    desig_parts = []
    for name, val in designated.items():
        desig_parts.append(f".{name} = {val}")
    init_str = ", ".join(desig_parts)
    lines.append(f"    struct S s = {{ {init_str} }};")

    # Verify each member
    idx = 1
    for name in members:
        expected = designated.get(name, 0)
        lines.append(f"    if (s.{name} != {expected}) return {idx};")
        idx += 1

    lines.append("    return 0;")
    lines.append("}")
    return "\n".join(lines)


def _generate_array_designated_init_code(size, designated):
    """Generate C code that initializes an array with designated initializers
    and verifies all elements.

    Returns 0 on success, non-zero on first mismatch.
    """
    lines = []
    lines.append("int main(void) {")

    # Build designated initializer list
    desig_parts = []
    for idx, val in designated.items():
        desig_parts.append(f"[{idx}] = {val}")
    init_str = ", ".join(desig_parts)
    lines.append(f"    int a[{size}] = {{ {init_str} }};")

    # Verify each element
    check_idx = 1
    for i in range(size):
        expected = designated.get(i, 0)
        lines.append(f"    if (a[{i}] != {expected}) return {check_idx};")
        check_idx += 1

    lines.append("    return 0;")
    lines.append("}")
    return "\n".join(lines)


def _generate_invalid_member_code(invalid_name):
    """Generate C code with an invalid struct member designator."""
    return f"""\
struct S {{ int m0; int m1; }};
int main(void) {{
    struct S s = {{ .{invalid_name} = 42 }};
    return 0;
}}
"""


def _generate_oob_array_code(size, index):
    """Generate C code with an out-of-bounds array designator."""
    return f"""\
int main(void) {{
    int a[{size}] = {{ [{index}] = 42 }};
    return 0;
}}
"""


# ---------------------------------------------------------------------------
# Compile and run helper
# ---------------------------------------------------------------------------

def _compile_and_run(tmp_path, code):
    """Compile C code with pycc and run the resulting executable."""
    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)
    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(out_path))
    assert res.success, "compile failed:\n" + "\n".join(res.errors)
    p = subprocess.run([str(out_path)], check=False, timeout=5)
    return p.returncode


def _compile_should_fail(tmp_path, code):
    """Compile C code with pycc and verify it fails."""
    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)
    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(out_path))
    return not res.success


# ---------------------------------------------------------------------------
# Property 6: Struct designated initializer correctness
# ---------------------------------------------------------------------------

class TestStructDesignatedInitProperties:
    """Property 6: Struct designated initializer correctness

    **Validates: Requirements 5.1, 5.3, 5.4, 5.5**
    """

    @given(data=struct_layout_and_designated_values())
    @settings(max_examples=100, deadline=None)
    def test_struct_designated_init_correctness(self, tmp_path_factory, data):
        """For any struct type and any subset of members with designated values,
        designated members should have the specified values and undesignated
        members should be zero.

        **Validates: Requirements 5.1, 5.3**
        """
        members, designated = data
        tmp_path = tmp_path_factory.mktemp("test")
        code = _generate_struct_designated_init_code(members, designated)
        rc = _compile_and_run(tmp_path, code)
        assert rc == 0, (
            f"Mismatch at check {rc} for struct members={members}, "
            f"designated={designated}\n\nGenerated code:\n{code}"
        )


# ---------------------------------------------------------------------------
# Property 7: Array designated initializer correctness
# ---------------------------------------------------------------------------

class TestArrayDesignatedInitProperties:
    """Property 7: Array designated initializer correctness

    **Validates: Requirements 5.2, 5.3**
    """

    @given(data=array_layout_and_designated_values())
    @settings(max_examples=100, deadline=None)
    def test_array_designated_init_correctness(self, tmp_path_factory, data):
        """For any array size and any subset of indices with designated values,
        designated elements should have the specified values and undesignated
        elements should be zero.

        **Validates: Requirements 5.2, 5.3**
        """
        size, designated = data
        tmp_path = tmp_path_factory.mktemp("test")
        code = _generate_array_designated_init_code(size, designated)
        rc = _compile_and_run(tmp_path, code)
        assert rc == 0, (
            f"Mismatch at check {rc} for array size={size}, "
            f"designated={designated}\n\nGenerated code:\n{code}"
        )


# ---------------------------------------------------------------------------
# Property 8: Invalid designated initializer rejection
# ---------------------------------------------------------------------------

class TestInvalidDesignatedInitProperties:
    """Property 8: Invalid designated initializer rejection

    **Validates: Requirements 5.6**
    """

    @given(invalid_name=invalid_member_names)
    @settings(max_examples=100, deadline=None)
    def test_invalid_struct_member_rejected(self, tmp_path_factory, invalid_name):
        """For any invalid member name (not in the struct definition),
        the compiler should produce a compilation error.

        **Validates: Requirements 5.6**
        """
        tmp_path = tmp_path_factory.mktemp("test")
        code = _generate_invalid_member_code(invalid_name)
        assert _compile_should_fail(tmp_path, code), (
            f"Compiler should reject invalid member name '{invalid_name}' "
            f"but compilation succeeded.\n\nGenerated code:\n{code}"
        )

    @given(data=oob_array_index())
    @settings(max_examples=100, deadline=None)
    def test_oob_array_index_rejected(self, tmp_path_factory, data):
        """For any out-of-bounds array index, the compiler should produce
        a compilation error.

        **Validates: Requirements 5.6**
        """
        size, index = data
        tmp_path = tmp_path_factory.mktemp("test")
        code = _generate_oob_array_code(size, index)
        assert _compile_should_fail(tmp_path, code), (
            f"Compiler should reject OOB index {index} for array size {size} "
            f"but compilation succeeded.\n\nGenerated code:\n{code}"
        )
