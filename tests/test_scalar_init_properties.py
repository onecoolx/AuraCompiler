# Feature: initializer-lowering, Property 1: Scalar Initialization Correctness
# **Validates: Requirements 2.1**
#
# For any scalar type (int, char, short, long) and any valid initialization
# value, compile and run a program containing that initialization, then verify
# the variable's value equals the initializer value.

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


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Each entry: (C type name, printf format, min value, max value)
SCALAR_TYPES = [
    ("int",   "%d",  -(2**31),     2**31 - 1),
    ("short", "%d",  -(2**15),     2**15 - 1),
    ("long",  "%ld", -(2**63),     2**63 - 1),
    ("char",  "%d",  -128,         127),
]


def _scalar_type_and_value():
    """Strategy that produces (c_type, fmt, value) tuples."""
    return st.sampled_from(SCALAR_TYPES).flatmap(
        lambda t: st.tuples(
            st.just(t[0]),
            st.just(t[1]),
            st.integers(min_value=t[2], max_value=t[3]),
        )
    )


# ---------------------------------------------------------------------------
# Property test
# ---------------------------------------------------------------------------

@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(data=_scalar_type_and_value())
def test_scalar_init_correctness(tmp_path_factory, data):
    """Property 1: Scalar Initialization Correctness.

    For any scalar type and any valid value within its range, a local
    variable initialized to that value should hold exactly that value
    at runtime.
    """
    c_type, fmt, value = data
    tmp_path = tmp_path_factory.mktemp("scalar")

    # Suffix for long literals
    literal = str(value)
    if c_type == "long":
        literal += "L"

    code = (
        f'extern int printf(const char *, ...);\n'
        f'int main(void) {{\n'
        f'    {c_type} x = {literal};\n'
        f'    printf("{fmt}\\n", {"(int)x" if c_type in ("char", "short") else "x"});\n'
        f'    return 0;\n'
        f'}}\n'
    )

    output = _compile_and_run(tmp_path, code)
    assert output == str(value), (
        f"Expected {value} for {c_type} x = {literal}, got {output!r}"
    )
