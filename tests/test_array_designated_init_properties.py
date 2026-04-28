# Feature: initializer-lowering, Property 8: Array Designated Initializer Correctness
#
# **Validates: Requirements 5.2, 5.5**
#
# For any array size and any index subset with designated initialization values,
# compile and run, verify designated indices have specified values and
# unspecified indices are zero.

import subprocess
from pathlib import Path

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from pycc.compiler import Compiler


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _compile_and_run(tmp_path: Path, code: str) -> int:
    """Compile *code* with pycc, run the binary, return exit code."""
    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)

    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(out_path))
    assert res.success, "compile failed: " + "\n".join(res.errors)

    p = subprocess.run([str(out_path)], check=False, timeout=10)
    return p.returncode


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

@st.composite
def array_designated_init_data(draw):
    """Generate an array size N (3-8) and a random non-empty subset of
    indices each mapped to a value in [1, 100].

    Returns (size, designated) where:
      size: int array size
      designated: dict mapping index -> value
    """
    size = draw(st.integers(min_value=3, max_value=8))
    indices = list(range(size))
    subset_size = draw(st.integers(min_value=1, max_value=size - 1))
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
        # Use [1, 100] so designated values are distinguishable from zero
        designated[idx] = draw(st.integers(min_value=1, max_value=100))
    return size, designated


# ---------------------------------------------------------------------------
# C code generation
# ---------------------------------------------------------------------------

def _generate_array_designated_code(size, designated):
    """Build C code that initializes int a[size] with designated initializers
    and checks every element via return code.

    Returns 0 on success, non-zero index (1-based) on first mismatch.
    """
    lines = [
        "int main(void) {",
    ]

    # Build designated initializer list
    desig_parts = []
    for idx in sorted(designated):
        desig_parts.append(f"[{idx}] = {designated[idx]}")
    init_str = ", ".join(desig_parts)
    lines.append(f"    int a[{size}] = {{ {init_str} }};")

    # Verify each element
    for i in range(size):
        expected = designated.get(i, 0)
        lines.append(f"    if (a[{i}] != {expected}) return {i + 1};")

    lines.append("    return 0;")
    lines.append("}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Property 8: Array Designated Initializer Correctness
# ---------------------------------------------------------------------------

@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(data=array_designated_init_data())
def test_array_designated_init_correctness(tmp_path_factory, data):
    """Property 8: Array Designated Initializer Correctness.

    For any array size and any index subset with designated initialization
    values, compile and run, verify designated indices have specified values
    and unspecified indices are zero.

    **Validates: Requirements 5.2, 5.5**
    """
    size, designated = data
    tmp_path = tmp_path_factory.mktemp("arr_desig")
    code = _generate_array_designated_code(size, designated)
    rc = _compile_and_run(tmp_path, code)
    assert rc == 0, (
        f"Mismatch at element {rc - 1} for array size={size}, "
        f"designated={designated}\n\nGenerated code:\n{code}"
    )
