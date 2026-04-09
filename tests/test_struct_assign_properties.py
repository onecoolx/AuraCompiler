"""Property-based tests for struct/union by-value assignment and value semantics.

**Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5**

Property 1: 结构体/联合体按值赋值保持成员值
For any 结构体或联合体类型（包含任意数量和类型的成员，包括嵌套结构体和联合体）
和任意成员值，执行 b = a 赋值或 struct S b = a 初始化后，b 的每个字节应与 a
的对应字节相等。

Property 2: 结构体参数值语义（调用方隔离）
For any 结构体类型和任意成员值，将结构体按值传递给函数后，无论被调用函数如何
修改其参数副本，调用方的原始结构体的所有成员值应保持不变。

Testing approach: use Hypothesis to generate random struct/union layouts with
integer-type members (int, long, short, char), generate C code that exercises
assignment and parameter passing, compile with pycc, run the executable, and
check return code (0 = success).
"""

import subprocess

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from pycc.compiler import Compiler


# ---------------------------------------------------------------------------
# C type descriptors: (c_type, size, alignment)
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

    Values are kept small (0-100) so they fit in a return code.
    """
    n = draw(st.integers(min_value=min_members, max_value=max_members))
    members = []
    for i in range(n):
        c_type, size, align = draw(st.sampled_from(INTEGER_MEMBER_TYPES))
        if c_type == "char":
            val = draw(st.integers(min_value=0, max_value=20))
        else:
            val = draw(st.integers(min_value=0, max_value=100))
        members.append((f"m{i}", c_type, val))
    return members


@st.composite
def nested_struct_members(draw):
    """Generate an outer struct with a nested inner struct.

    Returns (inner_members, outer_extra_members) where inner_members are
    the members of the nested struct and outer_extra_members are additional
    members of the outer struct.
    """
    inner = draw(struct_members(min_members=1, max_members=3))
    outer_extra = draw(struct_members(min_members=1, max_members=3))
    # Rename outer extras to avoid name collisions
    outer_extra = [(f"o{i}", ct, v) for i, (_, ct, v) in enumerate(outer_extra)]
    return inner, outer_extra


@st.composite
def union_members(draw, min_members=2, max_members=4):
    """Generate union members. The value is set via the first member."""
    n = draw(st.integers(min_value=min_members, max_value=max_members))
    members = []
    for i in range(n):
        c_type, size, align = draw(st.sampled_from(INTEGER_MEMBER_TYPES))
        members.append((f"m{i}", c_type, size))
    return members


# ---------------------------------------------------------------------------
# C code generation helpers
# ---------------------------------------------------------------------------

def _generate_assign_code(members):
    """Generate C code that tests b = a assignment for a flat struct.

    Returns 0 on success, member index + 1 on first mismatch.
    """
    lines = []
    lines.append("struct S {")
    for name, c_type, _ in members:
        lines.append(f"    {c_type} {name};")
    lines.append("};")
    lines.append("")
    lines.append("int main(void) {")
    lines.append("    struct S a;")
    for name, _, val in members:
        lines.append(f"    a.{name} = {val};")
    lines.append("    struct S b;")
    lines.append("    b = a;")
    for i, (name, _, val) in enumerate(members):
        lines.append(f"    if ((int)b.{name} != {val}) return {i + 1};")
    lines.append("    return 0;")
    lines.append("}")
    return "\n".join(lines)


def _generate_init_code(members):
    """Generate C code that tests struct S b = a initialization.

    Returns 0 on success, member index + 1 on first mismatch.
    """
    lines = []
    lines.append("struct S {")
    for name, c_type, _ in members:
        lines.append(f"    {c_type} {name};")
    lines.append("};")
    lines.append("")
    lines.append("int main(void) {")
    lines.append("    struct S a;")
    for name, _, val in members:
        lines.append(f"    a.{name} = {val};")
    lines.append("    struct S b = a;")
    for i, (name, _, val) in enumerate(members):
        lines.append(f"    if ((int)b.{name} != {val}) return {i + 1};")
    lines.append("    return 0;")
    lines.append("}")
    return "\n".join(lines)


def _generate_nested_assign_code(inner_members, outer_extra):
    """Generate C code that tests nested struct assignment b = a.

    Returns 0 on success, non-zero on mismatch.
    """
    lines = []
    lines.append("struct Inner {")
    for name, c_type, _ in inner_members:
        lines.append(f"    {c_type} {name};")
    lines.append("};")
    lines.append("struct Outer {")
    lines.append("    struct Inner in;")
    for name, c_type, _ in outer_extra:
        lines.append(f"    {c_type} {name};")
    lines.append("};")
    lines.append("")
    lines.append("int main(void) {")
    lines.append("    struct Outer a;")
    for name, _, val in inner_members:
        lines.append(f"    a.in.{name} = {val};")
    for name, _, val in outer_extra:
        lines.append(f"    a.{name} = {val};")
    lines.append("    struct Outer b;")
    lines.append("    b = a;")
    idx = 1
    for name, _, val in inner_members:
        lines.append(f"    if ((int)b.in.{name} != {val}) return {idx};")
        idx += 1
    for name, _, val in outer_extra:
        lines.append(f"    if ((int)b.{name} != {val}) return {idx};")
        idx += 1
    lines.append("    return 0;")
    lines.append("}")
    return "\n".join(lines)


def _generate_union_assign_code(members, value):
    """Generate C code that tests union assignment b = a.

    Sets the first member to `value`, assigns b = a, reads back via first member.
    Returns 0 if match, 1 otherwise.
    """
    lines = []
    lines.append("union U {")
    for name, c_type, _ in members:
        lines.append(f"    {c_type} {name};")
    lines.append("};")
    lines.append("")
    lines.append("int main(void) {")
    lines.append("    union U a;")
    first_name = members[0][0]
    lines.append(f"    a.{first_name} = {value};")
    lines.append("    union U b;")
    lines.append("    b = a;")
    lines.append(f"    if ((int)b.{first_name} != {value}) return 1;")
    lines.append("    return 0;")
    lines.append("}")
    return "\n".join(lines)


def _generate_caller_isolation_code(members):
    """Generate C code that tests caller isolation (Property 2).

    Passes struct by value to a function that modifies all members.
    Verifies caller's original struct is unchanged.
    Returns 0 on success, member index + 1 on first mismatch.
    """
    lines = []
    lines.append("struct S {")
    for name, c_type, _ in members:
        lines.append(f"    {c_type} {name};")
    lines.append("};")
    lines.append("")
    lines.append("void modify(struct S s) {")
    for name, c_type, _ in members:
        # Set to a different value to ensure modification
        lines.append(f"    s.{name} = 99;")
    lines.append("}")
    lines.append("")
    lines.append("int main(void) {")
    lines.append("    struct S a;")
    for name, _, val in members:
        lines.append(f"    a.{name} = {val};")
    lines.append("    modify(a);")
    for i, (name, _, val) in enumerate(members):
        lines.append(f"    if ((int)a.{name} != {val}) return {i + 1};")
    lines.append("    return 0;")
    lines.append("}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Compile and run helper
# ---------------------------------------------------------------------------

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
# Property 1: 结构体/联合体按值赋值保持成员值
# ---------------------------------------------------------------------------

class TestStructAssignProperties:
    """Property 1: 结构体/联合体按值赋值保持成员值

    **Validates: Requirements 1.1, 1.2, 1.3, 1.4**
    """

    @given(members=struct_members(min_members=1, max_members=6))
    @settings(max_examples=100, deadline=None)
    def test_struct_assign_preserves_values(self, tmp_path_factory, members):
        """b = a assignment preserves all member values for any flat struct.

        **Validates: Requirements 1.1**
        """
        tmp_path = tmp_path_factory.mktemp("test")
        code = _generate_assign_code(members)
        rc = _compile_and_run(tmp_path, code)
        assert rc == 0, (
            f"Member mismatch at index {rc - 1} for struct with members "
            f"{[(n, t, v) for n, t, v in members]}\n\nGenerated code:\n{code}"
        )

    @given(members=struct_members(min_members=1, max_members=6))
    @settings(max_examples=100, deadline=None)
    def test_struct_init_preserves_values(self, tmp_path_factory, members):
        """struct S b = a initialization preserves all member values.

        **Validates: Requirements 1.4**
        """
        tmp_path = tmp_path_factory.mktemp("test")
        code = _generate_init_code(members)
        rc = _compile_and_run(tmp_path, code)
        assert rc == 0, (
            f"Member mismatch at index {rc - 1} for struct with members "
            f"{[(n, t, v) for n, t, v in members]}\n\nGenerated code:\n{code}"
        )

    @given(data=nested_struct_members())
    @settings(max_examples=100, deadline=None)
    def test_nested_struct_assign_preserves_values(self, tmp_path_factory, data):
        """Nested struct assignment b = a recursively copies all members.

        **Validates: Requirements 1.2**
        """
        inner_members, outer_extra = data
        tmp_path = tmp_path_factory.mktemp("test")
        code = _generate_nested_assign_code(inner_members, outer_extra)
        rc = _compile_and_run(tmp_path, code)
        assert rc == 0, (
            f"Mismatch at check {rc} for nested struct\n"
            f"inner={[(n, t, v) for n, t, v in inner_members]}\n"
            f"outer_extra={[(n, t, v) for n, t, v in outer_extra]}\n"
            f"\nGenerated code:\n{code}"
        )

    @given(
        members=union_members(min_members=2, max_members=4),
        value=st.integers(min_value=0, max_value=100),
    )
    @settings(max_examples=100, deadline=None)
    def test_union_assign_preserves_value(self, tmp_path_factory, members, value):
        """Union b = a assignment copies the full union size.

        **Validates: Requirements 1.3**
        """
        tmp_path = tmp_path_factory.mktemp("test")
        code = _generate_union_assign_code(members, value)
        rc = _compile_and_run(tmp_path, code)
        assert rc == 0, (
            f"Union assign mismatch for members "
            f"{[(n, t) for n, t, _ in members]}, value={value}\n"
            f"\nGenerated code:\n{code}"
        )


# ---------------------------------------------------------------------------
# Property 2: 结构体参数值语义（调用方隔离）
# ---------------------------------------------------------------------------

class TestStructCallerIsolationProperties:
    """Property 2: 结构体参数值语义（调用方隔离）

    **Validates: Requirements 1.5**
    """

    @given(members=struct_members(min_members=1, max_members=6))
    @settings(max_examples=100, deadline=None)
    def test_caller_struct_unchanged_after_callee_modifies(self, tmp_path_factory, members):
        """Passing struct by value to a function that modifies it does not
        affect the caller's original struct.

        **Validates: Requirements 1.5**
        """
        tmp_path = tmp_path_factory.mktemp("test")
        code = _generate_caller_isolation_code(members)
        rc = _compile_and_run(tmp_path, code)
        assert rc == 0, (
            f"Caller isolation violated at member index {rc - 1} for struct "
            f"{[(n, t, v) for n, t, v in members]}\n\nGenerated code:\n{code}"
        )
