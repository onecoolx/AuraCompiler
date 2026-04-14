"""Tests for function pointer array declarations.

Covers C89 §6.5.4: declarators like void (*table[])(int) — array of
function pointers.
"""
import subprocess
from pycc.compiler import Compiler


def _compile_and_run(tmp_path, code):
    c = tmp_path / "t.c"
    o = tmp_path / "t"
    c.write_text(code)
    res = Compiler(optimize=False).compile_file(str(c), str(o))
    assert res.success, "compile failed: " + "\n".join(res.errors)
    p = subprocess.run([str(o)], check=False, timeout=5)
    return p.returncode


def _compile_only(tmp_path, code):
    """Parse + semantic analysis only (no IR/codegen)."""
    c = tmp_path / "t.c"
    c.write_text(code)
    comp = Compiler(optimize=False)
    try:
        tokens = comp.get_tokens(code)
        ast = comp.get_ast(tokens)
        ctx, analyzer = comp.analyze_semantics(ast)
        return len(analyzer.errors) == 0
    except Exception:
        return False


# ── Parsing ───────────────────────────────────────────────────────────

def test_fnptr_array_global_parse(tmp_path):
    """void (*table[])(int) at global scope should parse."""
    code = """
void f(int x) {}
void g(int x) {}
void (*table[])(int) = { f, g };
int main(void) { return 0; }
"""
    assert _compile_only(tmp_path, code)


def test_fnptr_array_static_parse(tmp_path):
    """static void (*table[])(int, int) should parse."""
    code = """
int add(int a, int b) { return a + b; }
int sub(int a, int b) { return a - b; }
static int (*ops[])(int, int) = { add, sub };
int main(void) { return 0; }
"""
    assert _compile_only(tmp_path, code)


def test_fnptr_array_no_size_parse(tmp_path):
    """void (*table[])(void) with inferred size should parse."""
    code = """
void nop(void) {}
static void (*table[])(void) = { nop };
int main(void) { return 0; }
"""
    assert _compile_only(tmp_path, code)


def test_fnptr_array_with_size_parse(tmp_path):
    """int (*table[2])(int) with explicit size should parse."""
    code = """
int inc(int x) { return x + 1; }
int dec(int x) { return x - 1; }
int (*table[2])(int) = { inc, dec };
int main(void) { return 0; }
"""
    assert _compile_only(tmp_path, code)


# ── typedef of function pointer ───────────────────────────────────────

def test_typedef_fnptr_with_const_params(tmp_path):
    """typedef int (*cmp)(const void *, const void *) should parse."""
    code = """
typedef int (*compar_fn_t)(const void *, const void *);
int main(void) { return 0; }
"""
    assert _compile_only(tmp_path, code)


def test_typedef_fnptr_void_return(tmp_path):
    """typedef void (*callback)(int) should parse."""
    code = """
typedef void (*callback_t)(int);
int main(void) { return 0; }
"""
    assert _compile_only(tmp_path, code)


# ── struct with function pointer member ───────────────────────────────

def test_struct_fnptr_member(tmp_path):
    """struct with int (*member)(int, int) should parse."""
    code = """
struct Ops {
    int (*add)(int, int);
    int (*sub)(int, int);
};
int main(void) { return 0; }
"""
    assert _compile_only(tmp_path, code)


# ── struct multi-declarator members ───────────────────────────────────

def test_struct_multi_decl_members(tmp_path):
    """struct { int a, b, c; } should parse all three members."""
    code = """
struct S { int a, b, c; };
int main(void) {
    struct S s;
    s.a = 1; s.b = 2; s.c = 3;
    return (s.a + s.b + s.c) == 6 ? 0 : 1;
}
"""
    assert _compile_and_run(tmp_path, code) == 0


def test_struct_multi_decl_with_pointer(tmp_path):
    """struct { int x, *p; } should parse mixed scalar and pointer."""
    code = """
struct S { int x, *p; };
int main(void) {
    struct S s;
    s.x = 42;
    s.p = &s.x;
    return *s.p == 42 ? 0 : 1;
}
"""
    assert _compile_and_run(tmp_path, code) == 0


# ── struct with 2D array member ───────────────────────────────────────

def test_struct_2d_array_member(tmp_path):
    """struct { float m[4][4]; } should parse."""
    code = """
struct Matrix { float m[4][4]; };
int main(void) { return 0; }
"""
    assert _compile_only(tmp_path, code)


# ── inline keyword ────────────────────────────────────────────────────

def test_static_inline_function(tmp_path):
    """static inline int f(int x) should parse and compile."""
    code = """
static inline int square(int x) { return x * x; }
int main(void) { return square(3) == 9 ? 0 : 1; }
"""
    assert _compile_and_run(tmp_path, code) == 0


# ── anonymous struct/union member ─────────────────────────────────────

def test_anonymous_union_member(tmp_path):
    """struct with anonymous union member should parse."""
    code = """
struct S {
    int tag;
    union { int i; float f; };
    int extra;
};
int main(void) { return 0; }
"""
    assert _compile_only(tmp_path, code)
