"""Tests for va_arg builtin in user-defined variadic functions.

Covers:
- Basic consecutive va_arg calls (state consistency)
- Overflow path when > 6 GP arguments are passed
- 32-bit int type correct load width
- Edge cases: exactly at register boundary, first overflow, many args
"""
import subprocess
from pycc.compiler import Compiler


def _compile_and_run(tmp_path, code: str) -> int:
    c_path = tmp_path / "t.c"
    out_path = tmp_path / "t"
    c_path.write_text(code)
    comp = Compiler(optimize=False)
    res = comp.compile_file(str(c_path), str(out_path))
    assert res.success, "compile failed: " + "\n".join(res.errors)
    p = subprocess.run([str(out_path)], check=False, timeout=5)
    return p.returncode


# ---------------------------------------------------------------------------
# Existing basic tests
# ---------------------------------------------------------------------------

def test_va_arg_sum_two_ints(tmp_path):
    """User variadic function that sums two int args via va_arg."""
    code = r"""
typedef __builtin_va_list va_list;
void __builtin_va_start(va_list ap, ...);
void __builtin_va_end(va_list ap);
int __builtin_va_arg_int(va_list ap);

int sum2(int n, ...) {
    va_list ap;
    __builtin_va_start(ap, n);
    int a = __builtin_va_arg_int(ap);
    int b = __builtin_va_arg_int(ap);
    __builtin_va_end(ap);
    return a + b;
}

int main(void) {
    return sum2(2, 10, 20);
}
"""
    assert _compile_and_run(tmp_path, code) == 30


def test_va_arg_sum_three_ints(tmp_path):
    """User variadic function that sums three int args."""
    code = r"""
typedef __builtin_va_list va_list;
void __builtin_va_start(va_list ap, ...);
void __builtin_va_end(va_list ap);
int __builtin_va_arg_int(va_list ap);

int sum3(int n, ...) {
    va_list ap;
    __builtin_va_start(ap, n);
    int a = __builtin_va_arg_int(ap);
    int b = __builtin_va_arg_int(ap);
    int c = __builtin_va_arg_int(ap);
    __builtin_va_end(ap);
    return a + b + c;
}

int main(void) {
    return sum3(3, 1, 2, 3);
}
"""
    assert _compile_and_run(tmp_path, code) == 6


# ---------------------------------------------------------------------------
# Consecutive va_arg state consistency (Requirement 4.4)
# ---------------------------------------------------------------------------

def test_va_arg_five_consecutive_calls(tmp_path):
    """Five consecutive va_arg calls maintain correct state ordering.

    With 1 named param (n -> rdi), variadic args occupy rsi..r9 (5 register
    slots). This uses all 5 register-passed variadic slots.
    """
    code = r"""
typedef __builtin_va_list va_list;
void __builtin_va_start(va_list ap, ...);
void __builtin_va_end(va_list ap);
int __builtin_va_arg_int(va_list ap);

int check5(int n, ...) {
    va_list ap;
    __builtin_va_start(ap, n);
    int a = __builtin_va_arg_int(ap);
    int b = __builtin_va_arg_int(ap);
    int c = __builtin_va_arg_int(ap);
    int d = __builtin_va_arg_int(ap);
    int e = __builtin_va_arg_int(ap);
    __builtin_va_end(ap);
    /* Verify each arg was extracted in order */
    if (a != 10) return 1;
    if (b != 20) return 2;
    if (c != 30) return 3;
    if (d != 40) return 4;
    if (e != 50) return 5;
    return 0;
}

int main(void) {
    return check5(5, 10, 20, 30, 40, 50);
}
"""
    assert _compile_and_run(tmp_path, code) == 0


# ---------------------------------------------------------------------------
# Register boundary: exactly fill all GP register slots (Requirement 4.2)
# ---------------------------------------------------------------------------

def test_va_arg_exactly_at_register_boundary(tmp_path):
    """With 1 named param, 5 variadic args exactly fill the register slots.

    gp_offset starts at 8 (1 named), and after 5 va_arg calls reaches 48.
    This is the boundary case — no overflow needed.
    """
    code = r"""
typedef __builtin_va_list va_list;
void __builtin_va_start(va_list ap, ...);
void __builtin_va_end(va_list ap);
int __builtin_va_arg_int(va_list ap);

int sum_boundary(int n, ...) {
    va_list ap;
    __builtin_va_start(ap, n);
    int total = 0;
    total = total + __builtin_va_arg_int(ap);
    total = total + __builtin_va_arg_int(ap);
    total = total + __builtin_va_arg_int(ap);
    total = total + __builtin_va_arg_int(ap);
    total = total + __builtin_va_arg_int(ap);
    __builtin_va_end(ap);
    return total;
}

int main(void) {
    /* 1+2+3+4+5 = 15 */
    return sum_boundary(5, 1, 2, 3, 4, 5);
}
"""
    assert _compile_and_run(tmp_path, code) == 15


# ---------------------------------------------------------------------------
# Overflow path: 7th GP arg goes to stack (Requirement 4.3)
# ---------------------------------------------------------------------------

def test_va_arg_first_overflow_arg(tmp_path):
    """6 variadic args with 1 named param: the 6th variadic arg overflows.

    Named: n -> rdi. Variadic: rsi, rdx, rcx, r8, r9 (5 in regs),
    6th variadic arg goes to stack via overflow_arg_area.
    """
    code = r"""
typedef __builtin_va_list va_list;
void __builtin_va_start(va_list ap, ...);
void __builtin_va_end(va_list ap);
int __builtin_va_arg_int(va_list ap);

int check_overflow(int n, ...) {
    va_list ap;
    __builtin_va_start(ap, n);
    int a = __builtin_va_arg_int(ap);
    int b = __builtin_va_arg_int(ap);
    int c = __builtin_va_arg_int(ap);
    int d = __builtin_va_arg_int(ap);
    int e = __builtin_va_arg_int(ap);
    int f = __builtin_va_arg_int(ap);  /* overflow path */
    __builtin_va_end(ap);
    if (a != 1) return 1;
    if (b != 2) return 2;
    if (c != 3) return 3;
    if (d != 4) return 4;
    if (e != 5) return 5;
    if (f != 6) return 6;
    return 0;
}

int main(void) {
    return check_overflow(6, 1, 2, 3, 4, 5, 6);
}
"""
    assert _compile_and_run(tmp_path, code) == 0


def test_va_arg_multiple_overflow_args(tmp_path):
    """8 variadic args: 5 in registers, 3 on stack via overflow.

    Verifies consecutive overflow_arg_area advances work correctly.
    """
    code = r"""
typedef __builtin_va_list va_list;
void __builtin_va_start(va_list ap, ...);
void __builtin_va_end(va_list ap);
int __builtin_va_arg_int(va_list ap);

int check_many(int n, ...) {
    va_list ap;
    __builtin_va_start(ap, n);
    int a = __builtin_va_arg_int(ap);
    int b = __builtin_va_arg_int(ap);
    int c = __builtin_va_arg_int(ap);
    int d = __builtin_va_arg_int(ap);
    int e = __builtin_va_arg_int(ap);
    int f = __builtin_va_arg_int(ap);  /* overflow 1 */
    int g = __builtin_va_arg_int(ap);  /* overflow 2 */
    int h = __builtin_va_arg_int(ap);  /* overflow 3 */
    __builtin_va_end(ap);
    if (a != 11) return 1;
    if (b != 22) return 2;
    if (c != 33) return 3;
    if (d != 44) return 4;
    if (e != 55) return 5;
    if (f != 66) return 6;
    if (g != 77) return 7;
    if (h != 88) return 8;
    return 0;
}

int main(void) {
    return check_many(8, 11, 22, 33, 44, 55, 66, 77, 88);
}
"""
    assert _compile_and_run(tmp_path, code) == 0


# ---------------------------------------------------------------------------
# 32-bit int load width (Requirement 4.5)
# ---------------------------------------------------------------------------

def test_va_arg_small_int_values(tmp_path):
    """Verify small int values (fitting in 32 bits) are loaded correctly.

    Tests that va_arg doesn't corrupt values due to incorrect load width.
    Uses values that would be wrong if sign-extended or zero-extended incorrectly.
    """
    code = r"""
typedef __builtin_va_list va_list;
void __builtin_va_start(va_list ap, ...);
void __builtin_va_end(va_list ap);
int __builtin_va_arg_int(va_list ap);

int check_ints(int n, ...) {
    va_list ap;
    __builtin_va_start(ap, n);
    int a = __builtin_va_arg_int(ap);
    int b = __builtin_va_arg_int(ap);
    int c = __builtin_va_arg_int(ap);
    __builtin_va_end(ap);
    if (a != 0) return 1;
    if (b != 1) return 2;
    if (c != 127) return 3;
    return 0;
}

int main(void) {
    return check_ints(3, 0, 1, 127);
}
"""
    assert _compile_and_run(tmp_path, code) == 0


def test_va_arg_negative_int_values(tmp_path):
    """Verify negative int values are correctly extracted via va_arg.

    Return code is limited to 0-255, so we use comparison-based checks.
    """
    code = r"""
typedef __builtin_va_list va_list;
void __builtin_va_start(va_list ap, ...);
void __builtin_va_end(va_list ap);
int __builtin_va_arg_int(va_list ap);

int check_neg(int n, ...) {
    va_list ap;
    __builtin_va_start(ap, n);
    int a = __builtin_va_arg_int(ap);
    int b = __builtin_va_arg_int(ap);
    __builtin_va_end(ap);
    /* -1 + 1 = 0, -42 + 42 = 0 */
    if (a + 1 != 0) return 1;
    if (b + 42 != 0) return 2;
    return 0;
}

int main(void) {
    return check_neg(2, -1, -42);
}
"""
    assert _compile_and_run(tmp_path, code) == 0


# ---------------------------------------------------------------------------
# Mixed: register + overflow with value verification (Req 4.1-4.4)
# ---------------------------------------------------------------------------

def test_va_arg_sum_with_overflow(tmp_path):
    """Sum 7 variadic args (5 register + 2 overflow), verify total."""
    code = r"""
typedef __builtin_va_list va_list;
void __builtin_va_start(va_list ap, ...);
void __builtin_va_end(va_list ap);
int __builtin_va_arg_int(va_list ap);

int sum7(int n, ...) {
    va_list ap;
    __builtin_va_start(ap, n);
    int total = 0;
    total = total + __builtin_va_arg_int(ap);
    total = total + __builtin_va_arg_int(ap);
    total = total + __builtin_va_arg_int(ap);
    total = total + __builtin_va_arg_int(ap);
    total = total + __builtin_va_arg_int(ap);
    total = total + __builtin_va_arg_int(ap);
    total = total + __builtin_va_arg_int(ap);
    __builtin_va_end(ap);
    return total;
}

int main(void) {
    /* 10+20+30+40+50+60+70 = 280, but return code is mod 256 = 24 */
    int r = sum7(7, 10, 20, 30, 40, 50, 60, 70);
    /* Use a simpler sum that fits in 0-255 */
    return r;
}
"""
    # 10+20+30+40+50+60+70 = 280; exit code = 280 % 256 = 24
    assert _compile_and_run(tmp_path, code) == 24


def test_va_arg_two_named_params_with_overflow(tmp_path):
    """Two named params consume 2 GP regs, leaving 4 for variadic.

    5th variadic arg overflows to stack. Verifies gp_offset starts at 16.
    """
    code = r"""
typedef __builtin_va_list va_list;
void __builtin_va_start(va_list ap, ...);
void __builtin_va_end(va_list ap);
int __builtin_va_arg_int(va_list ap);

int check2named(int x, int y, ...) {
    va_list ap;
    __builtin_va_start(ap, y);
    int a = __builtin_va_arg_int(ap);
    int b = __builtin_va_arg_int(ap);
    int c = __builtin_va_arg_int(ap);
    int d = __builtin_va_arg_int(ap);
    int e = __builtin_va_arg_int(ap);  /* overflow */
    __builtin_va_end(ap);
    if (a != 1) return 1;
    if (b != 2) return 2;
    if (c != 3) return 3;
    if (d != 4) return 4;
    if (e != 5) return 5;
    return 0;
}

int main(void) {
    return check2named(100, 200, 1, 2, 3, 4, 5);
}
"""
    assert _compile_and_run(tmp_path, code) == 0
