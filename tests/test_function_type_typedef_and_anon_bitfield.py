"""Test function type typedef and anonymous bitfield parsing.

Regression tests for sqlite3.c parsing:
- typedef __ssize_t cookie_read_function_t (void *, char *, size_t);
- int :32;  (anonymous bitfield padding)
"""

import subprocess, sys, textwrap, pytest


def _compile(src: str, tmp_path):
    c_file = tmp_path / "test.c"
    c_file.write_text(textwrap.dedent(src))
    cmd = [sys.executable, "pycc.py", "-c", str(c_file), "-o", str(tmp_path / "test.o")]
    return subprocess.run(cmd, capture_output=True, text=True)


def test_function_type_typedef(tmp_path):
    src = """\
    typedef long read_func_t (void *cookie, char *buf, unsigned long n);
    typedef int close_func_t (void *cookie);
    int x;
    """
    r = _compile(src, tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr


def test_function_type_typedef_with_const_params(tmp_path):
    src = """\
    typedef long write_func_t (void *cookie, const char *buf, unsigned long n);
    int x;
    """
    r = _compile(src, tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr


def test_anonymous_bitfield_padding(tmp_path):
    src = """\
    struct S {
        int x;
        int :32;
        int y;
    };
    """
    r = _compile(src, tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr


def test_multiple_anonymous_bitfields(tmp_path):
    src = """\
    struct Timex {
        int tai;
        int :32; int :32; int :32; int :32;
        int :32; int :32; int :32;
    };
    """
    r = _compile(src, tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr


def test_post_type_const_in_fnptr_param(tmp_path):
    """char const * inside function pointer parameter list."""
    src = """\
    void f(void(*)(void *, int, char const *, char const *, long));
    int x;
    """
    r = _compile(src, tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
