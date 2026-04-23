"""Test that const-qualified struct/union/enum types parse correctly as
struct members, function parameters, local variables, and global variables.

Regression: ``const struct Foo *p`` inside a struct body was rejected with
"Expected member name" because _parse_type_specifier checked the stale
``tok`` (pointing at ``const``) instead of ``self.current_token`` (pointing
at ``struct``) when deciding whether to enter the struct/union branch.
"""

import subprocess, sys, textwrap, pytest


def _compile(src: str, tmp_path, extra_flags=None):
    """Helper: write *src* to a temp .c file and compile with pycc -c."""
    c_file = tmp_path / "test.c"
    c_file.write_text(textwrap.dedent(src))
    cmd = [sys.executable, "pycc.py", "-c", str(c_file), "-o", str(tmp_path / "test.o")]
    if extra_flags:
        cmd.extend(extra_flags)
    return subprocess.run(cmd, capture_output=True, text=True)


class TestConstStructMember:
    """const struct T *member inside a struct body."""

    def test_const_struct_pointer_member(self, tmp_path):
        src = """\
        struct Methods { int version; };
        struct File {
            const struct Methods *pMethods;
        };
        int f(struct File *p) { return p->pMethods->version; }
        """
        r = _compile(src, tmp_path)
        assert r.returncode == 0, r.stdout + r.stderr

    def test_volatile_struct_pointer_member(self, tmp_path):
        src = """\
        struct Data { int x; };
        struct Wrapper {
            volatile struct Data *ptr;
        };
        """
        r = _compile(src, tmp_path)
        assert r.returncode == 0, r.stdout + r.stderr

    def test_const_union_member(self, tmp_path):
        src = """\
        union Val { int i; float f; };
        struct S {
            const union Val *v;
        };
        """
        r = _compile(src, tmp_path)
        assert r.returncode == 0, r.stdout + r.stderr

    def test_const_enum_member(self, tmp_path):
        src = """\
        enum Color { RED, GREEN, BLUE };
        struct S {
            const enum Color c;
        };
        """
        r = _compile(src, tmp_path)
        assert r.returncode == 0, r.stdout + r.stderr


class TestConstStructParam:
    """const struct T *param in function parameters."""

    def test_const_struct_pointer_param(self, tmp_path):
        src = """\
        struct Foo { int x; };
        int bar(const struct Foo *p) { return p->x; }
        """
        r = _compile(src, tmp_path)
        assert r.returncode == 0, r.stdout + r.stderr


class TestConstStructLocal:
    """const struct T local variable."""

    def test_const_struct_local(self, tmp_path):
        src = """\
        struct Pt { int x; int y; };
        int f(void) {
            const struct Pt p = {1, 2};
            return p.x;
        }
        """
        r = _compile(src, tmp_path)
        assert r.returncode == 0, r.stdout + r.stderr


class TestConstStructGlobal:
    """const struct T at file scope."""

    def test_const_struct_global(self, tmp_path):
        src = """\
        struct Cfg { int val; };
        const struct Cfg default_cfg = {42};
        """
        r = _compile(src, tmp_path)
        assert r.returncode == 0, r.stdout + r.stderr
