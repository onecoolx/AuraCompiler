"""Tests for nested struct member access and struct-to-member copy.

Covers:
- Typedef'd struct members recognized as aggregates (addr_of_member vs load_member)
- Nested member access: s.inner.field
- Struct-by-value copy to a member: s.inner = *ptr
- Function pointer calls through nested struct members: s.hooks.fn(args)
- Global typedef'd struct initializer with zero/NULL values
"""
import subprocess, textwrap, pytest

PYCC = "python3 pycc.py"

def _compile_run(tmp_path, code, extra_flags=""):
    src = tmp_path / "test.c"
    exe = tmp_path / "test_exe"
    src.write_text(textwrap.dedent(code))
    cmd = f"{PYCC} {src} -o {exe} {extra_flags}"
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, f"Compile failed: {r.stderr}"
    r2 = subprocess.run(str(exe), capture_output=True, text=True, timeout=10)
    return r2


class TestNestedStructMemberAccess:
    def test_typedef_struct_member_addr_not_load(self, tmp_path):
        """Accessing a typedef'd struct member should compute address, not dereference."""
        r = _compile_run(tmp_path, """\
            typedef struct { int x; int y; } inner_t;
            typedef struct { int a; inner_t b; } outer_t;
            int main(void) {
                outer_t s;
                s.a = 1;
                s.b.x = 42;
                s.b.y = 99;
                return (s.b.x == 42 && s.b.y == 99) ? 0 : 1;
            }
        """)
        assert r.returncode == 0

    def test_fnptr_through_nested_member(self, tmp_path):
        """Function pointer calls through nested struct members."""
        r = _compile_run(tmp_path, """\
            #include <stdio.h>
            #include <stdlib.h>
            #include <string.h>
            typedef struct {
                void *(*alloc)(long);
                void (*dealloc)(void *);
            } hooks_t;
            typedef struct {
                char *buf;
                long len;
                hooks_t hooks;
            } ctx_t;
            static void *my_alloc(long n) { return malloc(n); }
            static void my_free(void *p) { free(p); }
            int main(void) {
                ctx_t c;
                memset(&c, 0, sizeof(c));
                c.hooks.alloc = my_alloc;
                c.hooks.dealloc = my_free;
                c.buf = (char*)c.hooks.alloc(64);
                strcpy(c.buf, "hello");
                printf("%s\\n", c.buf);
                c.hooks.dealloc(c.buf);
                return 0;
            }
        """)
        assert r.returncode == 0
        assert "hello" in r.stdout

    def test_struct_copy_to_member(self, tmp_path):
        """Struct-by-value copy to a nested member: s.inner = *ptr."""
        r = _compile_run(tmp_path, """\
            #include <stdio.h>
            #include <stdlib.h>
            #include <string.h>
            typedef struct {
                void *(*alloc)(long);
                void (*dealloc)(void *);
                void *(*realloc_fn)(void *, long);
            } hooks_t;
            typedef struct {
                char *buf;
                long len;
                hooks_t hooks;
            } ctx_t;
            static void *my_alloc(long n) { return malloc(n); }
            static void my_free(void *p) { free(p); }
            static void *my_realloc(void *p, long n) { return realloc(p, n); }
            static hooks_t ghooks;
            int do_work(hooks_t *hk) {
                ctx_t c;
                char *nb;
                memset(&c, 0, sizeof(c));
                c.hooks = *hk;
                c.buf = (char*)c.hooks.alloc(64);
                if (c.buf == 0) return 1;
                strcpy(c.buf, "world");
                c.len = 5;
                nb = (char*)c.hooks.realloc_fn(c.buf, c.len + 1);
                if (nb == 0) { c.hooks.dealloc(c.buf); return 1; }
                printf("%s\\n", nb);
                c.hooks.dealloc(nb);
                return 0;
            }
            int main(void) {
                ghooks.alloc = my_alloc;
                ghooks.dealloc = my_free;
                ghooks.realloc_fn = my_realloc;
                return do_work(&ghooks);
            }
        """)
        assert r.returncode == 0
        assert "world" in r.stdout

    def test_global_typedef_struct_zero_init(self, tmp_path):
        """Global typedef'd struct initialized with {0, 0}."""
        r = _compile_run(tmp_path, """\
            #include <stdio.h>
            typedef unsigned long size_t2;
            typedef struct { const unsigned char *json; size_t2 position; } error;
            static error global_error = { 0, 0 };
            int main(void) {
                printf("%ld\\n", (long)global_error.position);
                return (global_error.json == 0 && global_error.position == 0) ? 0 : 1;
            }
        """)
        assert r.returncode == 0
        assert "0" in r.stdout
