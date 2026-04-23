"""Property-based tests for va_arg sequential extraction correctness.

**Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5**

Property 5: va_arg sequential extraction correctness
For any integer argument sequence (length 1 to 10, covering both register
passing and stack overflow paths), after passing to a variadic function,
each value extracted sequentially via va_arg should equal the corresponding
argument value passed in.

Testing approach: use Hypothesis to generate a list of 1-10 integer values
(range 0-100), generate C code with a variadic function that extracts N args
via va_arg and verifies each matches, compile with pycc, run the executable,
and check return code (0 = all match).
"""

import subprocess

from hypothesis import given, settings
from hypothesis import strategies as st

from pycc.compiler import Compiler


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

va_arg_values = st.lists(
    st.integers(min_value=0, max_value=100),
    min_size=1,
    max_size=10,
)


# ---------------------------------------------------------------------------
# C code generation
# ---------------------------------------------------------------------------

def _generate_va_arg_check_code(values) -> str:
    """Generate C code that passes `values` as variadic args and verifies
    each one is extracted correctly via va_arg in order.

    Returns 0 on success, index+1 on first mismatch.
    """
    n = len(values)
    lines = []
    lines.append("typedef __builtin_va_list va_list;")
    lines.append("void __builtin_va_start(va_list ap, ...);")
    lines.append("void __builtin_va_end(va_list ap);")
    lines.append("int __builtin_va_arg_int(va_list ap);")
    lines.append("")
    lines.append("int check(int n, ...) {")
    lines.append("    va_list ap;")
    lines.append("    __builtin_va_start(ap, n);")
    for i in range(n):
        lines.append(f"    int v{i} = __builtin_va_arg_int(ap);")
    lines.append("    __builtin_va_end(ap);")
    for i, val in enumerate(values):
        lines.append(f"    if (v{i} != {val}) return {i + 1};")
    lines.append("    return 0;")
    lines.append("}")
    lines.append("")
    args_str = ", ".join(str(v) for v in values)
    lines.append("int main(void) {")
    lines.append(f"    return check({n}, {args_str});")
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
# Property 5: va_arg sequential extraction correctness
# ---------------------------------------------------------------------------

class TestVaArgSequentialExtraction:
    """Property 5: va_arg sequential extraction correctness

    **Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5**
    """

    @given(values=va_arg_values)
    @settings(max_examples=100, deadline=None)
    def test_va_arg_extracts_all_values_in_order(self, tmp_path_factory, values):
        """For any list of 1-10 integer args, va_arg extracts each value
        in the correct order, covering both register and stack overflow paths.

        With 1 named param (n), variadic args use rsi..r9 (5 register slots).
        Lists of length > 5 exercise the overflow_arg_area path.

        **Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5**
        """
        tmp_path = tmp_path_factory.mktemp("test")
        code = _generate_va_arg_check_code(values)
        rc = _compile_and_run(tmp_path, code)
        assert rc == 0, (
            f"va_arg mismatch at index {rc - 1}: expected {values[rc - 1]} "
            f"for values={values}\n\nGenerated code:\n{code}"
        )
