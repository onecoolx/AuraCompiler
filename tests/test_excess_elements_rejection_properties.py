# Feature: initializer-lowering, Property 9: Excess Elements Rejection
#
# **Validates: Requirements 3.3, 4.5**
#
# For any array size N and initializer list of length > N, or any struct
# with more elements than members, compilation should produce an error.

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
    # Verify the error message mentions "excess"
    err_text = " ".join(res.errors).lower()
    assert "excess" in err_text, (
        f"Expected 'excess' in error message, got: {res.errors}"
    )


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# (C type, min value, max value)
_ARRAY_ELEM_TYPES = [
    ("int",   -(2**15), 2**15 - 1),
    ("short", -(2**15), 2**15 - 1),
    ("long",  -(2**31), 2**31 - 1),
    ("char",  -128,     127),
]


def _excess_array_init():
    """Strategy: (c_type, array_size N, values of length N+extra).

    Generates array size N in [2,8] and initializer list of length N+1 to N+3.
    """
    return st.sampled_from(_ARRAY_ELEM_TYPES).flatmap(
        lambda t: st.integers(min_value=2, max_value=8).flatmap(
            lambda n: st.integers(min_value=n + 1, max_value=n + 3).flatmap(
                lambda count: st.lists(
                    st.integers(min_value=t[1], max_value=t[2]),
                    min_size=count,
                    max_size=count,
                ).map(lambda vals, _t=t, _n=n: (_t[0], _n, vals))
            )
        )
    )


# Number of struct members: 2-4
_STRUCT_MEMBER_COUNTS = st.integers(min_value=2, max_value=4)


def _excess_struct_init():
    """Strategy: (num_members, values of length num_members+1).

    Generates a struct with num_members int members and an initializer
    list with one extra element.
    """
    return _STRUCT_MEMBER_COUNTS.flatmap(
        lambda n: st.lists(
            st.integers(min_value=-1000, max_value=1000),
            min_size=n + 1,
            max_size=n + 1,
        ).map(lambda vals, _n=n: (_n, vals))
    )


# ---------------------------------------------------------------------------
# Property 9a: Excess elements in array initializer
# ---------------------------------------------------------------------------

@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(data=_excess_array_init())
def test_excess_array_elements_rejected(tmp_path_factory, data):
    """Property 9: Excess Elements Rejection (array).

    **Validates: Requirements 3.3**

    For any array size N and initializer list of length > N,
    compilation should produce an error.
    """
    c_type, n, values = data
    tmp_path = tmp_path_factory.mktemp("excess_arr")

    lits = []
    for v in values:
        s = str(v)
        if c_type == "long":
            s += "L"
        lits.append(s)
    init_str = "{" + ", ".join(lits) + "}"

    code = (
        f"int main(void) {{\n"
        f"    {c_type} a[{n}] = {init_str};\n"
        f"    return 0;\n"
        f"}}\n"
    )

    _compile_should_fail(tmp_path, code)


# ---------------------------------------------------------------------------
# Property 9b: Excess elements in struct initializer
# ---------------------------------------------------------------------------

@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(data=_excess_struct_init())
def test_excess_struct_elements_rejected(tmp_path_factory, data):
    """Property 9: Excess Elements Rejection (struct).

    **Validates: Requirements 4.5**

    For any struct with M members and an initializer list with more
    than M elements, compilation should produce an error.
    """
    num_members, values = data
    tmp_path = tmp_path_factory.mktemp("excess_st")

    # Generate struct definition with num_members int members
    members = "".join(f"    int m{i};\n" for i in range(num_members))
    init_str = "{" + ", ".join(str(v) for v in values) + "}"

    code = (
        f"struct S {{\n"
        f"{members}"
        f"}};\n"
        f"int main(void) {{\n"
        f"    struct S s = {init_str};\n"
        f"    return 0;\n"
        f"}}\n"
    )

    _compile_should_fail(tmp_path, code)
