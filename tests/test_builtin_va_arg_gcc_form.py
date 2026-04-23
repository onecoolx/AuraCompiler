"""Test __builtin_va_arg(ap, type) parsing — the GCC-expanded form of va_arg.

When using system cpp (gcc -E), the standard va_arg(ap, T) macro is expanded
to __builtin_va_arg(ap, T) where the second argument is a type name.  The
parser must recognize this GCC extension and rewrite it to the internal
__builtin_va_arg_int(ap) call that codegen understands.
"""

import subprocess, sys, textwrap, pytest


def _compile(src: str, tmp_path):
    c_file = tmp_path / "test.c"
    c_file.write_text(textwrap.dedent(src))
    cmd = [sys.executable, "pycc.py", "-c", str(c_file), "-o", str(tmp_path / "test.o")]
    return subprocess.run(cmd, capture_output=True, text=True)


def test_builtin_va_arg_int(tmp_path):
    """__builtin_va_arg(ap, int) — basic integer type."""
    src = """\
    typedef void *va_list;
    void __builtin_va_start(va_list ap, ...);
    void __builtin_va_end(va_list ap);
    int sum2(int n, ...) {
        va_list ap;
        __builtin_va_start(ap, n);
        int a = __builtin_va_arg(ap, int);
        int b = __builtin_va_arg(ap, int);
        __builtin_va_end(ap);
        return a + b;
    }
    """
    r = _compile(src, tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr


def test_builtin_va_arg_pointer(tmp_path):
    """__builtin_va_arg(ap, int*) — pointer type argument."""
    src = """\
    typedef void *va_list;
    void __builtin_va_start(va_list ap, ...);
    void __builtin_va_end(va_list ap);
    int test(int n, ...) {
        va_list ap;
        __builtin_va_start(ap, n);
        int *p = __builtin_va_arg(ap, int*);
        __builtin_va_end(ap);
        return *p;
    }
    """
    r = _compile(src, tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr


def test_builtin_va_arg_as_lvalue_deref(tmp_path):
    """*__builtin_va_arg(ap, int*) = val — used as lvalue via deref."""
    src = """\
    typedef void *va_list;
    void __builtin_va_start(va_list ap, ...);
    void __builtin_va_end(va_list ap);
    void store(int n, ...) {
        va_list ap;
        __builtin_va_start(ap, n);
        *__builtin_va_arg(ap, int*) = 42;
        __builtin_va_end(ap);
    }
    """
    r = _compile(src, tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
