"""Test parsing of nested function pointer struct members.

Regression: ``void (*(*xDlSym)(Foo*, void*, const char*))(void)`` inside a
struct body was rejected because the parser only handled simple ``(*name)``
function pointer members, not nested ``(*(*name)(params))(params)`` forms.
"""

import subprocess, sys, textwrap, pytest


def _compile(src: str, tmp_path, extra_flags=None):
    c_file = tmp_path / "test.c"
    c_file.write_text(textwrap.dedent(src))
    cmd = [sys.executable, "pycc.py", "-c", str(c_file), "-o", str(tmp_path / "test.o")]
    if extra_flags:
        cmd.extend(extra_flags)
    return subprocess.run(cmd, capture_output=True, text=True)


def test_nested_fnptr_member_sqlite3_xDlSym(tmp_path):
    """The exact pattern from sqlite3.c sqlite3_vfs struct."""
    src = """\
    struct Vfs { int iVersion; };
    struct VfsMethods {
        int (*xClose)(struct Vfs*);
        void (*(*xDlSym)(struct Vfs*, void*, const char *zSymbol))(void);
        void (*xDlClose)(struct Vfs*, void*);
    };
    """
    r = _compile(src, tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr


def test_nested_fnptr_member_returns_int_fnptr(tmp_path):
    """Nested fnptr returning int(*)(int)."""
    src = """\
    struct S {
        int (*(*getCallback)(void *ctx))(int arg);
    };
    """
    r = _compile(src, tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr


def test_simple_fnptr_member_still_works(tmp_path):
    """Ensure simple function pointer members are not broken."""
    src = """\
    struct Ops {
        int (*read)(void*, int);
        void (*write)(void*, const char*, int);
    };
    """
    r = _compile(src, tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
