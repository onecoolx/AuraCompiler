# Feature: initializer-lowering, Property 2: Array Initialization and Zero-Fill
# Feature: initializer-lowering, Property 3: Char Array String Initialization
# Feature: initializer-lowering, Property 4: Multi-dimensional Array Initialization
#
# **Validates: Requirements 3.1, 3.2, 3.4, 3.5, 3.6, 3.7**
#
# Property 2: For any array element type (int, char, short, long), any array
# size N, and any initializer list of length <= N, compile and run, verify
# first k elements match initializer values and remaining N-k elements are zero.
#
# Property 3: For any string literal and any array size >= strlen+1 (or omitted
# size), compile and run, verify char array contains string bytes + null
# terminator + zeros.
#
# Property 4: For any 2D array dimensions [R][C] and any nested or flat
# initializer list, compile and run, verify elements in row-major order match
# initializer values, unspecified elements are zero.

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

# (C type, printf format, min value, max value)
ARRAY_ELEM_TYPES = [
    ("int",   "%d",  -(2**15), 2**15 - 1),
    ("short", "%d",  -(2**15), 2**15 - 1),
    ("long",  "%ld", -(2**31), 2**31 - 1),
    ("char",  "%d",  -128,     127),
]


def _array_type_size_and_values():
    """Strategy: (c_type, fmt, array_size, values) where len(values) <= array_size."""
    return st.sampled_from(ARRAY_ELEM_TYPES).flatmap(
        lambda t: st.integers(min_value=2, max_value=8).flatmap(
            lambda n: st.lists(
                st.integers(min_value=t[2], max_value=t[3]),
                min_size=0,
                max_size=n,
            ).map(lambda vals, _t=t, _n=n: (_t[0], _t[1], _n, vals))
        )
    )


# Printable ASCII chars safe for C string literals (no backslash, quote, etc.)
_SAFE_CHARS = [chr(c) for c in range(32, 127) if chr(c) not in ('"', '\\', "'", '?')]


def _string_and_size():
    """Strategy: (string_content, array_size_or_None).

    array_size is either None (omitted, inferred) or >= len(string)+1.
    """
    return st.text(
        alphabet=st.sampled_from(_SAFE_CHARS),
        min_size=1,
        max_size=20,
    ).flatmap(
        lambda s: st.one_of(
            st.just((s, None)),  # omitted size
            st.integers(
                min_value=len(s) + 1,
                max_value=len(s) + 8,
            ).map(lambda n, _s=s: (_s, n)),
        )
    )


def _2d_dims_and_values():
    """Strategy: (rows, cols, nested_values) for 2D array init.

    nested_values is a list of rows, each row is a list of ints with len <= cols.
    Total rows provided <= R.
    """
    return st.integers(min_value=2, max_value=4).flatmap(
        lambda r: st.integers(min_value=2, max_value=4).flatmap(
            lambda c: st.lists(
                st.lists(
                    st.integers(min_value=-1000, max_value=1000),
                    min_size=0,
                    max_size=c,
                ),
                min_size=0,
                max_size=r,
            ).map(lambda rows, _r=r, _c=c: (_r, _c, rows))
        )
    )


# ---------------------------------------------------------------------------
# Property 2: Array Initialization and Zero-Fill
# ---------------------------------------------------------------------------

@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(data=_array_type_size_and_values())
def test_array_init_and_zero_fill(tmp_path_factory, data):
    """Property 2: Array Initialization and Zero-Fill.

    **Validates: Requirements 3.1, 3.2**

    For any array element type, any array size N, and any initializer list
    of length k <= N, the first k elements equal the initializer values and
    the remaining N-k elements are zero.
    """
    c_type, fmt, n, values = data
    k = len(values)
    tmp_path = tmp_path_factory.mktemp("arr")

    # Build initializer list
    if k == 0:
        init_str = "{0}"
    else:
        lits = []
        for v in values:
            s = str(v)
            if c_type == "long":
                s += "L"
            lits.append(s)
        init_str = "{" + ", ".join(lits) + "}"

    # Cast for printf if needed
    cast_open = "(int)" if c_type in ("char", "short") else ""

    code = (
        f'extern int printf(const char *, ...);\n'
        f'int main(void) {{\n'
        f'    {c_type} a[{n}] = {init_str};\n'
        f'    int i;\n'
        f'    for (i = 0; i < {n}; i++)\n'
        f'        printf("{fmt}\\n", {cast_open}a[i]);\n'
        f'    return 0;\n'
        f'}}\n'
    )

    output = _compile_and_run(tmp_path, code)
    lines = output.split("\n")
    assert len(lines) == n, f"Expected {n} lines, got {len(lines)}"

    for i in range(n):
        expected = values[i] if i < k else 0
        actual = int(lines[i])
        assert actual == expected, (
            f"a[{i}]: expected {expected}, got {actual} "
            f"(type={c_type}, size={n}, init={values})"
        )


# ---------------------------------------------------------------------------
# Property 3: Char Array String Initialization
# ---------------------------------------------------------------------------

@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(data=_string_and_size())
def test_char_array_string_init(tmp_path_factory, data):
    """Property 3: Char Array String Initialization.

    **Validates: Requirements 3.4, 3.5**

    For any string literal and any array size >= strlen+1 (or omitted size),
    the char array contains the string bytes, a null terminator, and zeros
    for the remaining positions.
    """
    string_content, array_size = data
    tmp_path = tmp_path_factory.mktemp("str")

    if array_size is None:
        decl = f'char s[] = "{string_content}";'
        effective_size = len(string_content) + 1
    else:
        decl = f'char s[{array_size}] = "{string_content}";'
        effective_size = array_size

    code = (
        f'extern int printf(const char *, ...);\n'
        f'int main(void) {{\n'
        f'    {decl}\n'
        f'    int i;\n'
        f'    for (i = 0; i < {effective_size}; i++)\n'
        f'        printf("%d\\n", (int)s[i]);\n'
        f'    return 0;\n'
        f'}}\n'
    )

    output = _compile_and_run(tmp_path, code)
    lines = output.split("\n")
    assert len(lines) == effective_size, (
        f"Expected {effective_size} lines, got {len(lines)}"
    )

    for i in range(effective_size):
        actual = int(lines[i])
        if i < len(string_content):
            expected = ord(string_content[i])
            assert actual == expected, (
                f"s[{i}]: expected {expected} ('{string_content[i]}'), got {actual}"
            )
        else:
            # null terminator and trailing zeros
            assert actual == 0, (
                f"s[{i}]: expected 0 (zero-fill), got {actual}"
            )


# ---------------------------------------------------------------------------
# Property 4: Multi-dimensional Array Initialization
# ---------------------------------------------------------------------------

@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(data=_2d_dims_and_values())
def test_multidim_array_init(tmp_path_factory, data):
    """Property 4: Multi-dimensional Array Initialization.

    **Validates: Requirements 3.6, 3.7**

    For any 2D array dimensions [R][C] and any nested initializer list,
    elements in row-major order match initializer values, and unspecified
    elements are zero.
    """
    rows, cols, nested_values = data
    tmp_path = tmp_path_factory.mktemp("md")

    # Build nested initializer: {{v,v},{v,v},...}
    row_strs = []
    for row_vals in nested_values:
        if len(row_vals) == 0:
            row_strs.append("{0}")
        else:
            row_strs.append("{" + ", ".join(str(v) for v in row_vals) + "}")

    if len(nested_values) == 0:
        init_str = "{{0}}"
    else:
        init_str = "{" + ", ".join(row_strs) + "}"

    code = (
        f'extern int printf(const char *, ...);\n'
        f'int main(void) {{\n'
        f'    int a[{rows}][{cols}] = {init_str};\n'
        f'    int r, c;\n'
        f'    for (r = 0; r < {rows}; r++)\n'
        f'        for (c = 0; c < {cols}; c++)\n'
        f'            printf("%d\\n", a[r][c]);\n'
        f'    return 0;\n'
        f'}}\n'
    )

    output = _compile_and_run(tmp_path, code)
    lines = output.split("\n")
    total = rows * cols
    assert len(lines) == total, f"Expected {total} lines, got {len(lines)}"

    idx = 0
    for r in range(rows):
        for c in range(cols):
            if r < len(nested_values) and c < len(nested_values[r]):
                expected = nested_values[r][c]
            else:
                expected = 0
            actual = int(lines[idx])
            assert actual == expected, (
                f"a[{r}][{c}]: expected {expected}, got {actual} "
                f"(dims=[{rows}][{cols}], init={nested_values})"
            )
            idx += 1
