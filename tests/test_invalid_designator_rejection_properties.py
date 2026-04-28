# Feature: initializer-lowering, Property 10: Invalid Designated Initializer Rejection
#
# **Validates: Requirements 5.6**
#
# For any non-existent struct member name or out-of-bounds array index
# used as a designator, compilation should produce an error.

from pathlib import Path

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from pycc.compiler import Compiler


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _compile_should_fail(tmp_path: Path, code: str) -> None:
    """Compile *code* with pycc and assert that compilation fails."""
    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)

    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(out_path))
    assert not res.success, (
        f"Expected compilation to fail but it succeeded.\nCode:\n{code}"
    )


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Known struct member names — the struct will always have exactly these
_STRUCT_MEMBERS = ["a", "b", "c"]

# Names that are guaranteed NOT to be in _STRUCT_MEMBERS
_INVALID_MEMBER_NAMES = st.text(
    alphabet="xyzwXYZW_",
    min_size=1,
    max_size=8,
).filter(lambda n: n not in _STRUCT_MEMBERS and n.isidentifier())


def _invalid_struct_designator():
    """Strategy: (invalid_member_name, value).

    Generates a non-existent member name to use as a designator on a
    struct with members {a, b, c}.
    """
    return st.tuples(
        _INVALID_MEMBER_NAMES,
        st.integers(min_value=-1000, max_value=1000),
    )


def _invalid_array_designator():
    """Strategy: (array_size N, out-of-bounds index).

    Generates array size N in [2,8] and an index >= N.
    """
    return st.integers(min_value=2, max_value=8).flatmap(
        lambda n: st.integers(min_value=n, max_value=n + 10).map(
            lambda idx, _n=n: (_n, idx)
        )
    )


# ---------------------------------------------------------------------------
# Property 10a: Invalid struct member designator
# ---------------------------------------------------------------------------

@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(data=_invalid_struct_designator())
def test_invalid_struct_member_designator_rejected(tmp_path_factory, data):
    """Property 10: Invalid Designated Initializer Rejection (struct member).

    **Validates: Requirements 5.6**

    For any non-existent struct member name used as a designator,
    compilation should produce an error.
    """
    bad_member, value = data
    tmp_path = tmp_path_factory.mktemp("inv_desig_s")

    code = (
        f"struct S {{\n"
        f"    int a;\n"
        f"    int b;\n"
        f"    int c;\n"
        f"}};\n"
        f"int main(void) {{\n"
        f"    struct S s = {{ .{bad_member} = {value} }};\n"
        f"    return 0;\n"
        f"}}\n"
    )

    _compile_should_fail(tmp_path, code)


# ---------------------------------------------------------------------------
# Property 10b: Out-of-bounds array index designator
# ---------------------------------------------------------------------------

@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(data=_invalid_array_designator())
def test_out_of_bounds_array_designator_rejected(tmp_path_factory, data):
    """Property 10: Invalid Designated Initializer Rejection (array index).

    **Validates: Requirements 5.6**

    For any out-of-bounds array index used as a designator,
    compilation should produce an error.
    """
    array_size, bad_index = data
    tmp_path = tmp_path_factory.mktemp("inv_desig_a")

    code = (
        f"int main(void) {{\n"
        f"    int a[{array_size}] = {{ [{bad_index}] = 42 }};\n"
        f"    return 0;\n"
        f"}}\n"
    )

    _compile_should_fail(tmp_path, code)
