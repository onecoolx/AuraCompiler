# Feature: initializer-lowering, Property 5: Struct Initialization and Zero-Fill
# Feature: initializer-lowering, Property 6: Union First Member Initialization
# Feature: initializer-lowering, Property 7: Struct Designated Initializer Correctness
#
# **Validates: Requirements 4.1, 4.2, 4.3, 4.4, 5.1, 5.3, 5.4, 5.5**
#
# Property 5: For any struct layout (with scalar members) and any initializer
# list of length <= member count, compile and run, verify specified members
# have correct values and unspecified members are zero.
#
# Property 6: For any union type and any initialization value, compile and run,
# verify the first member equals the initializer value.
#
# Property 7: For any struct type and any member subset with designated values,
# compile and run, verify designated members have specified values and
# unspecified members are zero.

import subprocess
from pathlib import Path

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from pycc.compiler import Compiler


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _compile_and_run(tmp_path: Path, code: str) -> str:
    """Compile *code* with pycc, run the binary, return stdout."""
    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)

    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(out_path))
    assert res.success, "compile failed: " + "\n".join(res.errors)

    p = subprocess.run(
        [str(out_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=10,
    )
    assert p.returncode == 0, f"runtime error (rc={p.returncode}): {p.stderr}"
    return p.stdout.strip()


# Member names pool (avoid C keywords)
_MEMBER_NAMES = ["a", "b", "c", "d"]


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

def _struct_members_and_values():
    """Strategy: (num_members, values) where len(values) <= num_members.

    Generates structs with 2-4 int members and 0 to num_members init values.
    Values are in a safe int range to avoid overflow issues.
    """
    return st.integers(min_value=2, max_value=4).flatmap(
        lambda n: st.lists(
            st.integers(min_value=-10000, max_value=10000),
            min_size=0,
            max_size=n,
        ).map(lambda vals, _n=n: (_n, vals))
    )


def _union_value():
    """Strategy: (num_members, value) for union first-member init.

    Generates unions with 2-3 members (all int for simplicity) and one value.
    """
    return st.tuples(
        st.integers(min_value=2, max_value=3),
        st.integers(min_value=-10000, max_value=10000),
    )


def _designated_struct():
    """Strategy: (num_members, designated_pairs) for designated init.

    designated_pairs is a list of (member_index, value) with unique indices,
    representing .member_name = value designators.
    """
    return st.integers(min_value=2, max_value=4).flatmap(
        lambda n: st.lists(
            st.tuples(
                st.integers(min_value=0, max_value=n - 1),
                st.integers(min_value=-10000, max_value=10000),
            ),
            min_size=1,
            max_size=n,
            unique_by=lambda pair: pair[0],
        ).map(lambda pairs, _n=n: (_n, pairs))
    )


# ---------------------------------------------------------------------------
# Property 5: Struct Initialization and Zero-Fill
# ---------------------------------------------------------------------------

@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(data=_struct_members_and_values())
def test_struct_init_and_zero_fill(tmp_path_factory, data):
    """Property 5: Struct Initialization and Zero-Fill.

    **Validates: Requirements 4.1, 4.2, 4.3**

    For any struct layout (with scalar members) and any initializer list of
    length <= member count, compile and run, verify specified members have
    correct values and unspecified members are zero.
    """
    num_members, values = data
    k = len(values)
    tmp_path = tmp_path_factory.mktemp("struct")

    # Build struct definition
    members = _MEMBER_NAMES[:num_members]
    member_decls = "\n".join(f"    int {m};" for m in members)

    # Build initializer
    if k == 0:
        init_str = "{0}"
    else:
        init_str = "{" + ", ".join(str(v) for v in values) + "}"

    # Build printf for each member
    prints = "\n".join(
        f'    printf("%d\\n", s.{m});' for m in members
    )

    code = (
        f'extern int printf(const char *, ...);\n'
        f'struct S {{\n'
        f'{member_decls}\n'
        f'}};\n'
        f'int main(void) {{\n'
        f'    struct S s = {init_str};\n'
        f'{prints}\n'
        f'    return 0;\n'
        f'}}\n'
    )

    output = _compile_and_run(tmp_path, code)
    lines = output.split("\n")
    assert len(lines) == num_members, (
        f"Expected {num_members} lines, got {len(lines)}"
    )

    for i in range(num_members):
        expected = values[i] if i < k else 0
        actual = int(lines[i])
        assert actual == expected, (
            f"s.{members[i]}: expected {expected}, got {actual} "
            f"(members={num_members}, init={values})"
        )


# ---------------------------------------------------------------------------
# Property 6: Union First Member Initialization
# ---------------------------------------------------------------------------

@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(data=_union_value())
def test_union_first_member_init(tmp_path_factory, data):
    """Property 6: Union First Member Initialization.

    **Validates: Requirements 4.4**

    For any union type and any initialization value, compile and run, verify
    the first member equals the initializer value.
    """
    num_members, value = data
    tmp_path = tmp_path_factory.mktemp("union")

    # Build union definition with int members
    members = _MEMBER_NAMES[:num_members]
    member_decls = "\n".join(f"    int {m};" for m in members)

    code = (
        f'extern int printf(const char *, ...);\n'
        f'union U {{\n'
        f'{member_decls}\n'
        f'}};\n'
        f'int main(void) {{\n'
        f'    union U u = {{{value}}};\n'
        f'    printf("%d\\n", u.{members[0]});\n'
        f'    return 0;\n'
        f'}}\n'
    )

    output = _compile_and_run(tmp_path, code)
    actual = int(output)
    assert actual == value, (
        f"u.{members[0]}: expected {value}, got {actual}"
    )


# ---------------------------------------------------------------------------
# Property 7: Struct Designated Initializer Correctness
# ---------------------------------------------------------------------------

@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(data=_designated_struct())
def test_struct_designated_init(tmp_path_factory, data):
    """Property 7: Struct Designated Initializer Correctness.

    **Validates: Requirements 5.1, 5.3, 5.4, 5.5**

    For any struct type and any member subset with designated values, compile
    and run, verify designated members have specified values and unspecified
    members are zero.
    """
    num_members, designated_pairs = data
    tmp_path = tmp_path_factory.mktemp("desig")

    members = _MEMBER_NAMES[:num_members]
    member_decls = "\n".join(f"    int {m};" for m in members)

    # Build designated initializer: {.a = 1, .c = 3}
    desig_strs = []
    for idx, val in designated_pairs:
        desig_strs.append(f".{members[idx]} = {val}")
    init_str = "{" + ", ".join(desig_strs) + "}"

    # Build printf for each member
    prints = "\n".join(
        f'    printf("%d\\n", s.{m});' for m in members
    )

    code = (
        f'extern int printf(const char *, ...);\n'
        f'struct S {{\n'
        f'{member_decls}\n'
        f'}};\n'
        f'int main(void) {{\n'
        f'    struct S s = {init_str};\n'
        f'{prints}\n'
        f'    return 0;\n'
        f'}}\n'
    )

    output = _compile_and_run(tmp_path, code)
    lines = output.split("\n")
    assert len(lines) == num_members, (
        f"Expected {num_members} lines, got {len(lines)}"
    )

    # Build expected values: designated members get their value, rest are 0
    expected_map = {idx: val for idx, val in designated_pairs}
    for i in range(num_members):
        expected = expected_map.get(i, 0)
        actual = int(lines[i])
        assert actual == expected, (
            f"s.{members[i]}: expected {expected}, got {actual} "
            f"(designated={designated_pairs})"
        )
