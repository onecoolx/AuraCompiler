"""Tests for va_arg builtin in user-defined variadic functions."""
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
